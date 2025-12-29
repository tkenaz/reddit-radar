"""Reddit Radar - Open source Reddit monitoring for lead generation."""
from .config import get_settings, Settings
from .notifier import get_notifier, Notification, Priority

__version__ = "1.0.0"
__all__ = ["get_settings", "Settings", "get_notifier", "Notification", "Priority"]
