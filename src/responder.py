"""
AI-powered response generation for Reddit posts.
Uses Claude Opus 4.5 for high-quality, contextual responses.
"""
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

from .config import get_settings
from .classifier import Intent, Classification


# Default paths
PROJECT_ROOT = Path(__file__).parent.parent
COMPANY_CONFIG = PROJECT_ROOT / "config" / "company.yaml"
PROMPT_CONFIG = PROJECT_ROOT / "config" / "system_prompt.yaml"


@dataclass
class DraftResponse:
    """Generated response draft."""
    content: str
    post_id: str
    post_title: str
    subreddit: str
    intent: Intent
    confidence: float
    model_used: str
    should_post: bool = False  # Always False - human approval required

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "post_id": self.post_id,
            "post_title": self.post_title,
            "subreddit": self.subreddit,
            "intent": self.intent.value,
            "confidence": self.confidence,
            "model_used": self.model_used,
            "should_post": self.should_post
        }


class Responder:
    """AI-powered response generator using Opus 4.5."""

    def __init__(self):
        self.settings = get_settings()
        self._client = None
        self._company_config = None
        self._prompt_config = None

    def _load_configs(self):
        """Load company and prompt configurations."""
        if self._company_config is None:
            if COMPANY_CONFIG.exists():
                with open(COMPANY_CONFIG, 'r') as f:
                    self._company_config = yaml.safe_load(f)
            else:
                self._company_config = {}

        if self._prompt_config is None:
            if PROMPT_CONFIG.exists():
                with open(PROMPT_CONFIG, 'r') as f:
                    self._prompt_config = yaml.safe_load(f)
            else:
                self._prompt_config = {
                    "model": "claude-opus-4-5-20251101",
                    "max_tokens": 500,
                    "system_prompt": "Generate helpful Reddit responses."
                }

    def _get_client(self):
        """Lazy-load Anthropic client."""
        if self._client is None:
            if not self.settings.ai.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")

            try:
                import anthropic
                self._client = anthropic.Anthropic(
                    api_key=self.settings.ai.anthropic_api_key
                )
            except ImportError:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")

        return self._client

    @property
    def is_available(self) -> bool:
        """Check if response generation is available."""
        return bool(self.settings.ai.anthropic_api_key)

    def _get_model(self) -> str:
        """Get model to use for response generation."""
        self._load_configs()
        return self._prompt_config.get("model", "claude-opus-4-5-20251101")

    def _build_context(self, post: Dict[str, Any], classification: Classification) -> str:
        """Build context for response generation."""
        self._load_configs()

        # Get relevant service info based on post content
        services_context = self._get_relevant_services(post)

        # Get subreddit-specific adjustments
        subreddit = post.get('subreddit', '')
        subreddit_adj = self._prompt_config.get('subreddit_adjustments', {}).get(subreddit, {})

        # Get intent-specific adjustments
        intent_adj = self._prompt_config.get('intent_adjustments', {}).get(
            classification.intent.value, {}
        )

        context = f"""## Post to Respond To
Title: {post.get('title', '')}
Subreddit: r/{subreddit}
Content: {post.get('selftext', '')[:1500] if post.get('selftext') else '[No body text]'}
Score: {post.get('score', 0)} | Comments: {post.get('num_comments', 0)}

## Classification
Intent: {classification.intent.value}
Confidence: {classification.confidence:.0%}
Reasoning: {classification.reasoning}

## Relevant Kenaz Services
{services_context}

## Subreddit Tone
{subreddit_adj.get('tone', 'professional, helpful')}
Can mention: {', '.join(subreddit_adj.get('can_mention', ['general expertise']))}

## Intent Approach
{intent_adj.get('approach', 'Be genuinely helpful.')}
"""
        return context

    def _get_relevant_services(self, post: Dict[str, Any]) -> str:
        """Get relevant services based on post content."""
        self._load_configs()

        text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
        services = self._company_config.get('services', {})

        relevant = []
        for service_key, service in services.items():
            keywords = service.get('keywords', [])
            if any(kw.lower() in text for kw in keywords):
                relevant.append(f"- {service.get('name')}: {service.get('value_prop')}")

        if not relevant:
            return "No specific service match. Focus on general expertise and helpfulness."

        return "\n".join(relevant)

    def generate_response(
        self,
        post: Dict[str, Any],
        classification: Classification
    ) -> Optional[DraftResponse]:
        """
        Generate a draft response for a Reddit post.

        Args:
            post: Reddit post data
            classification: Intent classification result

        Returns:
            DraftResponse or None if shouldn't respond
        """
        # Skip noise and low-confidence classifications
        if classification.intent == Intent.NOISE:
            return None

        if classification.intent == Intent.COMPETITOR:
            # Usually skip competitor posts
            return None

        if classification.confidence < 0.5:
            return None

        if not self.is_available:
            return None

        self._load_configs()

        try:
            client = self._get_client()
            model = self._get_model()

            system_prompt = self._prompt_config.get('system_prompt', '')
            context = self._build_context(post, classification)

            # Add style examples
            examples = self._prompt_config.get('style_examples', [])
            if examples:
                examples_text = "\n\n## Style Examples\n"
                for ex in examples[:2]:  # Limit to 2 examples
                    examples_text += f"\nContext: {ex.get('context', '')}\n"
                    examples_text += f"Response:\n{ex.get('response', '')}\n"
                context += examples_text

            response = client.messages.create(
                model=model,
                max_tokens=self._prompt_config.get('max_tokens', 500),
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": f"{context}\n\n---\n\nGenerate a response draft for this post. Remember: helpful first, never salesy. 100-200 words max."
                    }
                ]
            )

            content = response.content[0].text.strip()

            return DraftResponse(
                content=content,
                post_id=post.get('id', ''),
                post_title=post.get('title', ''),
                subreddit=post.get('subreddit', ''),
                intent=classification.intent,
                confidence=classification.confidence,
                model_used=model
            )

        except Exception as e:
            print(f"Response generation failed: {e}")
            return None

    def generate_batch(
        self,
        posts_with_classifications: list[tuple[Dict[str, Any], Classification]]
    ) -> list[DraftResponse]:
        """
        Generate responses for multiple posts.

        Args:
            posts_with_classifications: List of (post, classification) tuples

        Returns:
            List of DraftResponse objects
        """
        responses = []
        for post, classification in posts_with_classifications:
            response = self.generate_response(post, classification)
            if response:
                responses.append(response)
        return responses


def get_responder() -> Responder:
    """Get responder instance."""
    return Responder()
