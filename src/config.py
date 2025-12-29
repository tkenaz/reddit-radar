"""
Centralized configuration for Reddit Radar.
All settings loaded from environment variables.
"""
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class RedditConfig:
    """Reddit API configuration."""
    client_id: str
    client_secret: str
    username: str
    password: str
    user_agent: str = "RedditRadar:v1.0.0 (by /u/your_username)"

    @classmethod
    def from_env(cls) -> "RedditConfig":
        """Load Reddit config from environment."""
        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        username = os.getenv("REDDIT_USERNAME")
        password = os.getenv("REDDIT_PASSWORD")
        user_agent = os.getenv("REDDIT_USER_AGENT", cls.user_agent)

        missing = []
        if not client_id:
            missing.append("REDDIT_CLIENT_ID")
        if not client_secret:
            missing.append("REDDIT_CLIENT_SECRET")
        if not username:
            missing.append("REDDIT_USERNAME")
        if not password:
            missing.append("REDDIT_PASSWORD")

        if missing:
            raise ValueError(
                f"Missing required Reddit credentials: {', '.join(missing)}\n"
                f"Please set them in your .env file. See .env.example for reference."
            )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent=user_agent
        )


@dataclass
class TelegramConfig:
    """Telegram notification configuration."""
    bot_token: str
    chat_id: str
    enabled: bool = True

    @classmethod
    def from_env(cls) -> Optional["TelegramConfig"]:
        """Load Telegram config from environment. Returns None if not configured."""
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not bot_token or not chat_id:
            return None

        return cls(bot_token=bot_token, chat_id=chat_id)


@dataclass
class SlackConfig:
    """Slack notification configuration."""
    webhook_url: str
    enabled: bool = True

    @classmethod
    def from_env(cls) -> Optional["SlackConfig"]:
        """Load Slack config from environment. Returns None if not configured."""
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")

        if not webhook_url:
            return None

        return cls(webhook_url=webhook_url)


@dataclass
class EmailConfig:
    """Email notification configuration."""
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    from_address: str
    to_address: str
    enabled: bool = True

    @classmethod
    def from_env(cls) -> Optional["EmailConfig"]:
        """Load Email config from environment. Returns None if not configured."""
        smtp_host = os.getenv("SMTP_HOST")
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")
        to_address = os.getenv("EMAIL_TO")

        if not all([smtp_host, smtp_user, smtp_password, to_address]):
            return None

        return cls(
            smtp_host=smtp_host,
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            from_address=os.getenv("EMAIL_FROM", smtp_user),
            to_address=to_address
        )


@dataclass
class AIConfig:
    """AI classification configuration."""
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    model: str = "claude-haiku-4-5"  # Default to Haiku (cheap & fast)

    @classmethod
    def from_env(cls) -> "AIConfig":
        """Load AI config from environment."""
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model=os.getenv("AI_MODEL", cls.model)
        )

    @property
    def is_available(self) -> bool:
        """Check if any AI provider is configured."""
        return bool(self.anthropic_api_key or self.openai_api_key)


@dataclass
class DatabaseConfig:
    """PostgreSQL configuration."""
    host: str = "localhost"
    port: int = 5432
    database: str = "reddit_radar"
    user: str = "postgres"
    password: str = ""

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Load database config from environment."""
        return cls(
            host=os.getenv("PG_HOST", cls.host),
            port=int(os.getenv("PG_PORT", cls.port)),
            database=os.getenv("PG_DB", cls.database),
            user=os.getenv("PG_USER", cls.user),
            password=os.getenv("PG_PASSWORD", cls.password)
        )

    @property
    def connection_string(self) -> str:
        """Get PostgreSQL connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    api_requests_per_minute: int = 60
    min_seconds_between_posts: int = 600  # 10 minutes
    min_seconds_between_comments: int = 60  # 1 minute
    max_retries: int = 3
    retry_delay_seconds: int = 2


class Settings:
    """Main settings container."""

    def __init__(self):
        self.reddit = RedditConfig.from_env()
        self.telegram = TelegramConfig.from_env()
        self.slack = SlackConfig.from_env()
        self.email = EmailConfig.from_env()
        self.ai = AIConfig.from_env()
        self.database = DatabaseConfig.from_env()
        self.rate_limit = RateLimitConfig()

    @property
    def has_notifications(self) -> bool:
        """Check if any notification method is configured."""
        return any([self.telegram, self.slack, self.email])


# Global settings instance (lazy loaded)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
