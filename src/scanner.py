#!/usr/bin/env python3
"""
Reddit Radar Scanner - Automated lead discovery from Reddit.

Searches Reddit for relevant posts based on your keywords configuration
and sends notifications through your configured channels.

Usage:
  python -m src.scanner [--dry-run] [--config PATH]

Options:
  --dry-run     Print results to console instead of sending notifications
  --config      Path to keywords config file (default: config/keywords.yaml)
"""

import sys
import yaml
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from .reddit_client import RedditClient
from .notifier import get_notifier, Notification, Priority

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


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load keywords configuration from YAML file."""
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            f"Please copy config/keywords.yaml.example to config/keywords.yaml and customize it."
        )

    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def score_post(post: Dict[str, Any], config: Dict[str, Any]) -> float:
    """
    Calculate relevance score for a post.

    Scoring:
    - Base: score + (comments * 2)
    - Subreddit priority boost
    - Recency boost (newer posts scored higher)
    """
    base_score = post['score'] + (post['num_comments'] * 2)

    # Subreddit priority boost
    subreddit = post['subreddit']
    subreddit_prefs = config.get('subreddit_preferences', {})
    priority_boost = subreddit_prefs.get(subreddit, {}).get('priority_boost', 1.0)

    final_score = base_score * priority_boost

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
    unique_posts = {p['id']: p for p in all_posts}.values()

    # Score and sort
    scored_posts = [(score_post(p, config), p) for p in unique_posts]
    scored_posts.sort(reverse=True, key=lambda x: x[0])

    # Return top N
    max_posts = config.get('notification', {}).get('max_posts_per_category', 5)
    top_posts = [p for score, p in scored_posts[:max_posts]]

    logger.info(f"  Category result: {len(top_posts)} top posts selected")
    return top_posts


def format_results_message(
    results: Dict[str, List[Dict[str, Any]]],
    config: Dict[str, Any]
) -> str:
    """Format search results as notification message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    total_posts = sum(len(posts) for posts in results.values())

    if total_posts == 0:
        return "No relevant posts found in the last scan period."

    msg = f"Found {total_posts} posts across {len([r for r in results.values() if r])} categories:\n\n"

    for category_key, posts in results.items():
        if not posts:
            continue

        category = config['categories'][category_key]
        msg += f"**{category['name']}** ({category.get('priority', 'medium')} priority)\n"

        for i, post in enumerate(posts, 1):
            msg += f"\n{i}. {post['title'][:80]}{'...' if len(post['title']) > 80 else ''}\n"
            msg += f"   r/{post['subreddit']} | Score: {post['score']} | Comments: {post['num_comments']}\n"
            msg += f"   {post['url']}\n"

        msg += "\n---\n"

    return msg


def run_scan(config_path: Path = DEFAULT_CONFIG, dry_run: bool = False) -> Dict[str, Any]:
    """
    Run the Reddit scan.

    Args:
        config_path: Path to keywords configuration
        dry_run: If True, print to console instead of sending notifications

    Returns:
        Dict with scan results and stats
    """
    logger.info("=" * 60)
    logger.info("Reddit Radar Scan Starting")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'PRODUCTION'}")
    logger.info("=" * 60)

    # Load config
    config = load_config(config_path)
    logger.info(f"Loaded config with {len(config.get('categories', {}))} categories")

    # Initialize Reddit client
    client = RedditClient()
    logger.info("Reddit client initialized")

    # Search each category
    results = {}
    for category_key, category in config.get('categories', {}).items():
        posts = search_category(client, category, config)
        results[category_key] = posts

    # Calculate stats
    total_posts = sum(len(posts) for posts in results.values())
    stats = {
        "total_posts": total_posts,
        "categories_with_results": len([r for r in results.values() if r]),
        "timestamp": datetime.now().isoformat()
    }

    # Send notification
    if total_posts > 0:
        message = format_results_message(results, config)

        notifier = get_notifier(include_console=dry_run)
        notification = Notification(
            title=f"Reddit Radar: {total_posts} leads found",
            message=message,
            priority=Priority.HIGH if total_posts >= 10 else Priority.NORMAL
        )
        notifier.send(notification)

    logger.info("=" * 60)
    logger.info(f"Scan completed: {total_posts} posts found")
    logger.info("=" * 60)

    return {
        "results": results,
        "stats": stats
    }


def main():
    """CLI entry point."""
    dry_run = "--dry-run" in sys.argv

    # Parse config path
    config_path = DEFAULT_CONFIG
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            config_path = Path(sys.argv[idx + 1])

    try:
        run_scan(config_path=config_path, dry_run=dry_run)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"Scan failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
