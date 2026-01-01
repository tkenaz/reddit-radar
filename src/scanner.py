#!/usr/bin/env python3
"""
Reddit Radar Scanner - Automated lead discovery from Reddit.

Searches Reddit for relevant posts based on your keywords configuration,
classifies them by intent using AI, generates response drafts, and sends notifications.

Usage:
  python -m src.scanner [--dry-run] [--classify] [--respond] [--config PATH]

Options:
  --dry-run     Print results to console instead of sending notifications
  --classify    Enable AI intent classification (requires ANTHROPIC_API_KEY)
  --respond     Generate draft responses using Opus 4.5 (requires --classify)
  --config      Path to keywords config file (default: config/keywords.yaml)
"""

import sys
import yaml
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from .reddit_client import RedditClient
from .notifier import get_notifier, Notification, Priority, TelegramNotifier
from .classifier import get_classifier, Intent, Classification
from .responder import get_responder, DraftResponse
from .draft_store import get_draft_store
from .config import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Default paths
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "keywords.yaml"

# Intent emoji mapping
INTENT_EMOJI = {
    Intent.HOT_LEAD: "🔥",
    Intent.PARTNERSHIP: "🤝",
    Intent.CONTENT_IDEA: "💡",
    Intent.COMPETITOR: "👀",
    Intent.NOISE: "⚪",
}


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load keywords configuration from YAML file."""
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            f"Please copy config/keywords.yaml.example to config/keywords.yaml and customize it."
        )

    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def score_post(post: Dict[str, Any], config: Dict[str, Any], classification: Optional[Classification] = None) -> float:
    """
    Calculate relevance score for a post.

    Scoring:
    - Base: score + (comments * 2)
    - Subreddit priority boost
    - Intent boost (hot leads get 2x, partnerships 1.5x)
    """
    base_score = post['score'] + (post['num_comments'] * 2)

    # Subreddit priority boost
    subreddit = post['subreddit']
    subreddit_prefs = config.get('subreddit_preferences', {})
    priority_boost = subreddit_prefs.get(subreddit, {}).get('priority_boost', 1.0)

    # Intent boost
    intent_boost = 1.0
    if classification:
        if classification.intent == Intent.HOT_LEAD:
            intent_boost = 2.0 * classification.confidence
        elif classification.intent == Intent.PARTNERSHIP:
            intent_boost = 1.5 * classification.confidence
        elif classification.intent == Intent.CONTENT_IDEA:
            intent_boost = 1.2 * classification.confidence

    final_score = base_score * priority_boost * intent_boost

    return final_score


def search_category(
    client: RedditClient,
    category: Dict[str, Any],
    config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Search Reddit for posts in a specific category."""
    logger.info(f"Searching category: {category['name']}")

    all_posts = []
    keywords = category['keywords']
    subreddits = category['subreddits']

    search_config = config.get('search_config', {})
    time_filter = search_config.get('time_filter', 'day')
    results_per_query = search_config.get('results_per_query', 10)
    min_score = search_config.get('min_score', 5)
    min_comments = search_config.get('min_comments', 2)

    for keyword in keywords:
        for subreddit in subreddits:
            try:
                logger.info(f"  Searching '{keyword}' in r/{subreddit}")
                posts = client.search_posts(
                    query=keyword,
                    subreddit=subreddit,
                    time_filter=time_filter,
                    limit=results_per_query
                )

                # Filter by minimum engagement
                filtered_posts = [
                    p for p in posts
                    if p['score'] >= min_score
                    and p['num_comments'] >= min_comments
                ]

                logger.info(f"    Found {len(filtered_posts)} qualifying posts")
                all_posts.extend(filtered_posts)

            except Exception as e:
                logger.error(f"    Error searching '{keyword}' in r/{subreddit}: {e}")

    # Deduplicate by post ID
    unique_posts = list({p['id']: p for p in all_posts}.values())

    logger.info(f"  Category result: {len(unique_posts)} unique posts found")
    return unique_posts


def classify_posts(posts: List[Dict[str, Any]], use_ai: bool = True) -> List[tuple[Dict[str, Any], Classification]]:
    """Classify posts by intent."""
    classifier = get_classifier()

    if use_ai and classifier.is_available:
        logger.info(f"  Classifying {len(posts)} posts with AI...")
    else:
        logger.info(f"  Classifying {len(posts)} posts with rules (AI not available)...")

    results = []
    for post in posts:
        classification = classifier.classify(post)
        results.append((post, classification))
        logger.info(f"    {INTENT_EMOJI.get(classification.intent, '?')} {classification.intent.value}: {post['title'][:50]}...")

    return results


def generate_responses(
    posts_with_classifications: List[tuple[Dict[str, Any], Classification]]
) -> Dict[str, DraftResponse]:
    """Generate draft responses for actionable posts."""
    responder = get_responder()

    if not responder.is_available:
        logger.warning("Response generation not available (no API key)")
        return {}

    # Filter to actionable posts only
    actionable = [
        (p, c) for p, c in posts_with_classifications
        if c.is_actionable
    ]

    if not actionable:
        logger.info("  No actionable posts for response generation")
        return {}

    logger.info(f"  Generating responses for {len(actionable)} actionable posts (Opus 4.5)...")

    drafts = {}
    for post, classification in actionable:
        draft = responder.generate_response(post, classification)
        if draft:
            drafts[post['id']] = draft
            logger.info(f"    ✍️  Draft generated for: {post['title'][:40]}...")

    logger.info(f"  Generated {len(drafts)} draft responses")
    return drafts


def send_drafts_for_approval(
    drafts: Dict[str, DraftResponse],
    posts: Dict[str, Dict[str, Any]]
) -> int:
    """
    Save drafts to store and send to Telegram for approval.

    Returns number of drafts sent.
    """
    if not drafts:
        return 0

    settings = get_settings()
    if not settings.telegram:
        logger.warning("Telegram not configured, skipping draft approval notifications")
        return 0

    store = get_draft_store()
    telegram = TelegramNotifier(settings.telegram)

    sent_count = 0
    for post_id, draft in drafts.items():
        # Skip already processed posts
        if store.is_post_processed(post_id):
            logger.info(f"    ⏭️  Skipping (already processed): {posts.get(post_id, {}).get('title', '')[:40]}...")
            continue

        post = posts.get(post_id, {})

        # Save to store
        saved_draft = store.save_draft(
            post_id=post_id,
            post_url=post.get('url', ''),
            post_title=post.get('title', 'Unknown'),
            subreddit=post.get('subreddit', 'unknown'),
            content=draft.content,
            intent=draft.intent if isinstance(draft.intent, str) else str(draft.intent.value if hasattr(draft.intent, 'value') else draft.intent),
            confidence=draft.confidence,
        )

        # Send to Telegram with approval buttons
        message_id = telegram.send_draft_for_approval(
            draft_id=saved_draft.id,
            post_title=post.get('title', 'Unknown'),
            post_url=post.get('url', ''),
            subreddit=post.get('subreddit', 'unknown'),
            intent=draft.intent,
            confidence=draft.confidence,
            draft_content=draft.content,
            score=post.get('score', 0),
            comments=post.get('num_comments', 0),
        )

        if message_id:
            sent_count += 1
            logger.info(f"    📤 Sent for approval: {post.get('title', '')[:40]}...")

    logger.info(f"  Sent {sent_count} drafts for approval")
    return sent_count


def format_results_message(
    results: Dict[str, List[tuple[Dict[str, Any], Classification]]],
    config: Dict[str, Any],
    classify_enabled: bool = False,
    drafts: Dict[str, DraftResponse] = None
) -> str:
    """Format search results as notification message."""
    total_posts = sum(len(posts) for posts in results.values())
    drafts = drafts or {}

    if total_posts == 0:
        return "No relevant posts found in the last scan period."

    # Count by intent
    intent_counts = {intent: 0 for intent in Intent}
    for posts in results.values():
        for post, classification in posts:
            intent_counts[classification.intent] += 1

    msg = f"Found {total_posts} posts"
    if classify_enabled:
        hot = intent_counts[Intent.HOT_LEAD]
        partner = intent_counts[Intent.PARTNERSHIP]
        if hot or partner:
            msg += f" ({hot} 🔥 hot leads, {partner} 🤝 partnerships)"
    if drafts:
        msg += f" | ✍️ {len(drafts)} drafts"
    msg += ":\n\n"

    for category_key, posts in results.items():
        if not posts:
            continue

        category = config['categories'][category_key]
        msg += f"**{category['name']}** ({category.get('priority', 'medium')} priority)\n"

        for i, (post, classification) in enumerate(posts, 1):
            emoji = INTENT_EMOJI.get(classification.intent, "")
            title = post['title'][:70] + ('...' if len(post['title']) > 70 else '')

            msg += f"\n{i}. {emoji} {title}\n"
            msg += f"   r/{post['subreddit']} | ↑{post['score']} | 💬{post['num_comments']}"

            if classify_enabled and classification.confidence >= 0.5:
                msg += f" | {classification.intent.value} ({classification.confidence:.0%})"

            msg += f"\n   {post['url']}\n"

            # Add draft response if available
            if post['id'] in drafts:
                draft = drafts[post['id']]
                msg += f"\n   **Draft Response:**\n"
                # Indent draft content
                draft_lines = draft.content.split('\n')
                for line in draft_lines:
                    msg += f"   > {line}\n"
                msg += "\n"

        msg += "\n---\n"

    return msg


def run_scan(
    config_path: Path = DEFAULT_CONFIG,
    dry_run: bool = False,
    classify: bool = False,
    respond: bool = False
) -> Dict[str, Any]:
    """
    Run the Reddit scan.

    Args:
        config_path: Path to keywords configuration
        dry_run: If True, print to console instead of sending notifications
        classify: If True, use AI to classify post intents
        respond: If True, generate draft responses for actionable posts

    Returns:
        Dict with scan results and stats
    """
    logger.info("=" * 60)
    logger.info("Reddit Radar Scan Starting")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'PRODUCTION'}")
    logger.info(f"AI Classification: {'ENABLED' if classify else 'DISABLED'}")
    logger.info(f"Response Generation: {'ENABLED (Opus 4.5)' if respond else 'DISABLED'}")
    logger.info("=" * 60)

    # Load config
    config = load_config(config_path)
    logger.info(f"Loaded config with {len(config.get('categories', {}))} categories")

    # Initialize Reddit client
    client = RedditClient()
    logger.info("Reddit client initialized")

    # Search each category and classify
    results = {}
    for category_key, category in config.get('categories', {}).items():
        posts = search_category(client, category, config)

        # Classify posts
        classified_posts = classify_posts(posts, use_ai=classify)

        # Score with classification boost and sort
        scored_posts = [
            (score_post(p, config, c), p, c)
            for p, c in classified_posts
        ]
        scored_posts.sort(reverse=True, key=lambda x: x[0])

        # Take top N
        max_posts = config.get('notification', {}).get('max_posts_per_category', 5)
        top_posts = [(p, c) for score, p, c in scored_posts[:max_posts]]

        results[category_key] = top_posts

    # Calculate stats
    total_posts = sum(len(posts) for posts in results.values())
    hot_leads = sum(
        1 for posts in results.values()
        for p, c in posts
        if c.intent == Intent.HOT_LEAD
    )

    # Generate response drafts if enabled
    drafts = {}
    if respond and classify:
        all_classified = [
            (p, c) for posts in results.values()
            for p, c in posts
        ]
        drafts = generate_responses(all_classified)

        # Build post lookup for approval workflow
        all_posts = {p['id']: p for posts in results.values() for p, c in posts}

        # Send drafts for approval (with inline buttons)
        if drafts and not dry_run:
            send_drafts_for_approval(drafts, all_posts)

    stats = {
        "total_posts": total_posts,
        "hot_leads": hot_leads,
        "drafts_generated": len(drafts),
        "categories_with_results": len([r for r in results.values() if r]),
        "timestamp": datetime.now().isoformat()
    }

    # Send notification
    if total_posts > 0:
        message = format_results_message(
            results, config,
            classify_enabled=classify,
            drafts=drafts
        )

        notifier = get_notifier(include_console=dry_run)

        # Determine priority based on hot leads
        if hot_leads >= 3:
            priority = Priority.URGENT
        elif hot_leads >= 1:
            priority = Priority.HIGH
        else:
            priority = Priority.NORMAL

        title = f"Reddit Radar: {total_posts} posts ({hot_leads} 🔥 hot leads)"
        if drafts:
            title += f" | ✍️ {len(drafts)} drafts"

        notification = Notification(
            title=title,
            message=message,
            priority=priority
        )
        notifier.send(notification)

    logger.info("=" * 60)
    logger.info(f"Scan completed: {total_posts} posts, {hot_leads} hot leads, {len(drafts)} drafts")
    logger.info("=" * 60)

    return {
        "results": results,
        "drafts": drafts,
        "stats": stats
    }


def main():
    """CLI entry point."""
    dry_run = "--dry-run" in sys.argv
    classify = "--classify" in sys.argv
    respond = "--respond" in sys.argv

    # --respond requires --classify
    if respond and not classify:
        classify = True
        logger.info("Note: --respond implies --classify, enabling classification")

    # Parse config path
    config_path = DEFAULT_CONFIG
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            config_path = Path(sys.argv[idx + 1])

    try:
        run_scan(
            config_path=config_path,
            dry_run=dry_run,
            classify=classify,
            respond=respond
        )
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"Scan failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
