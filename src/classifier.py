"""
AI-powered intent classification for Reddit posts.
Uses Claude Haiku for cost-effective classification.
"""
import json
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass

from .config import get_settings


class Intent(Enum):
    """Classification of post author's intent."""
    HOT_LEAD = "hot_lead"           # Actively looking for solution/tool/service
    COMPETITOR = "competitor"        # Showcasing their own solution
    CONTENT_IDEA = "content_idea"    # Asking question (content opportunity)
    PARTNERSHIP = "partnership"      # Looking for contractor/agency/partner
    NOISE = "noise"                  # Not relevant for business


@dataclass
class Classification:
    """Result of intent classification."""
    intent: Intent
    confidence: float  # 0.0 - 1.0
    reasoning: str
    raw_response: Optional[str] = None

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= 0.7

    @property
    def is_actionable(self) -> bool:
        """Check if this classification warrants action."""
        return self.intent in [Intent.HOT_LEAD, Intent.PARTNERSHIP] and self.confidence >= 0.5


CLASSIFICATION_PROMPT = """Analyze this Reddit post and classify the author's intent.

Title: {title}
Subreddit: r/{subreddit}
Content: {content}

Classify into ONE of these categories:

1. HOT_LEAD - Author is actively looking for a solution, tool, or service.
   Signals: "looking for", "need help with", "recommendations?", "what tool do you use for"

2. COMPETITOR - Author is showcasing or promoting their own solution.
   Signals: "I built", "we launched", "check out my", "introducing"

3. CONTENT_IDEA - Author is asking a question that could become content.
   Signals: "how do I", "what's the best way", "why does", "explain"

4. PARTNERSHIP - Author is looking for contractor, agency, or partner.
   Signals: "hiring", "looking for developer", "need agency", "seeking partner"

5. NOISE - Not relevant for business purposes.
   Signals: memes, off-topic, complaints without asking for solution

Return ONLY valid JSON (no markdown):
{{"intent": "HOT_LEAD|COMPETITOR|CONTENT_IDEA|PARTNERSHIP|NOISE", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}"""


class Classifier:
    """AI-powered intent classifier."""

    def __init__(self):
        self.settings = get_settings()
        self._client = None

    @property
    def is_available(self) -> bool:
        """Check if AI classification is available."""
        return self.settings.ai.is_available

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

    def classify(self, post: Dict[str, Any]) -> Classification:
        """
        Classify a Reddit post's intent using AI.

        Args:
            post: Dict with 'title', 'subreddit', and optionally 'selftext'

        Returns:
            Classification result
        """
        if not self.is_available:
            return self._rule_based_classify(post)

        try:
            return self._ai_classify(post)
        except Exception as e:
            print(f"AI classification failed, falling back to rules: {e}")
            return self._rule_based_classify(post)

    def _ai_classify(self, post: Dict[str, Any]) -> Classification:
        """Classify using Claude Haiku."""
        client = self._get_client()

        content = post.get('selftext', '') or ''
        if len(content) > 1000:
            content = content[:1000] + "..."

        prompt = CLASSIFICATION_PROMPT.format(
            title=post.get('title', ''),
            subreddit=post.get('subreddit', ''),
            content=content
        )

        response = client.messages.create(
            model=self.settings.ai.model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        raw_text = response.content[0].text.strip()

        # Parse JSON response (handle markdown code blocks)
        try:
            # Remove markdown code block if present
            json_text = raw_text
            if json_text.startswith("```"):
                # Remove ```json or ``` at start
                json_text = json_text.split("\n", 1)[1] if "\n" in json_text else json_text[3:]
            if json_text.endswith("```"):
                json_text = json_text[:-3]
            json_text = json_text.strip()

            data = json.loads(json_text)
            intent = Intent(data['intent'].lower())
            confidence = float(data['confidence'])
            reasoning = data.get('reasoning', '')

            return Classification(
                intent=intent,
                confidence=min(max(confidence, 0.0), 1.0),
                reasoning=reasoning,
                raw_response=raw_text
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Failed to parse AI response: {raw_text}")
            return self._rule_based_classify(post)

    def _rule_based_classify(self, post: Dict[str, Any]) -> Classification:
        """Fallback rule-based classification when AI is not available."""
        title = post.get('title', '').lower()
        content = (post.get('selftext', '') or '').lower()
        text = f"{title} {content}"

        # Hot lead signals
        hot_lead_signals = [
            'looking for', 'need help', 'recommendations', 'suggest',
            'what tool', 'which software', 'any alternatives', 'best way to',
            'how do you handle', 'what do you use for'
        ]

        # Competitor signals
        competitor_signals = [
            'i built', 'we built', 'i made', 'we made', 'launched',
            'introducing', 'check out', 'i created', 'my project',
            'show hn', 'side project'
        ]

        # Partnership signals
        partnership_signals = [
            'hiring', 'looking for developer', 'need contractor',
            'seeking partner', 'looking for agency', 'freelancer needed'
        ]

        # Content idea signals
        content_signals = [
            'how do i', 'how to', 'why does', 'explain', 'what is',
            'eli5', 'help me understand', "what's the difference"
        ]

        # Check in order of priority
        if any(signal in text for signal in hot_lead_signals):
            return Classification(
                intent=Intent.HOT_LEAD,
                confidence=0.6,
                reasoning="Matched hot lead keywords (rule-based)"
            )

        if any(signal in text for signal in partnership_signals):
            return Classification(
                intent=Intent.PARTNERSHIP,
                confidence=0.6,
                reasoning="Matched partnership keywords (rule-based)"
            )

        if any(signal in text for signal in competitor_signals):
            return Classification(
                intent=Intent.COMPETITOR,
                confidence=0.6,
                reasoning="Matched competitor keywords (rule-based)"
            )

        if any(signal in text for signal in content_signals):
            return Classification(
                intent=Intent.CONTENT_IDEA,
                confidence=0.5,
                reasoning="Matched content idea keywords (rule-based)"
            )

        return Classification(
            intent=Intent.NOISE,
            confidence=0.4,
            reasoning="No strong signals detected (rule-based)"
        )

    def classify_batch(self, posts: list[Dict[str, Any]]) -> list[tuple[Dict[str, Any], Classification]]:
        """
        Classify multiple posts.

        Returns list of (post, classification) tuples.
        """
        results = []
        for post in posts:
            classification = self.classify(post)
            results.append((post, classification))
        return results


def get_classifier() -> Classifier:
    """Get classifier instance."""
    return Classifier()
