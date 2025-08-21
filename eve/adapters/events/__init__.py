"""Bus Module

Provides event publishing and subscription functionality with Redis as the message broker.
"""

from typing import Callable, Dict, Any, Optional, TypeVar, cast
import logging
from eve.adapters.events.redis_event_bus import RedisEventBus
import os

logger = logging.getLogger(__name__)

# Generic type for type annotation
handler_type = TypeVar("handler_type", bound=Callable[[Dict[str, Any]], None])


# Global event bus instance (will be initialized when first accessed)
_event_bus_instance: Optional[RedisEventBus] = None


def _get_event_bus() -> RedisEventBus:
    """Lazily get the event bus instance to avoid circular imports.

    Returns:
        RedisEventBus instance
    """
    global _event_bus_instance
    if _event_bus_instance is None:
        # Create a default Redis client if no container is available
        import redis

        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=os.getenv("REDIS_PORT", 6379),
            db=os.getenv("REDIS_DB", 0),
            password=os.getenv("REDIS_PASSWORD", None),
            decode_responses=True,
        )
        _event_bus_instance = RedisEventBus(redis_client)
    return _event_bus_instance


def set_event_bus(event_bus: RedisEventBus):
    """Set a custom event bus instance.

    This is useful when integrating with dependency injection frameworks.

    Args:
        event_bus: RedisEventBus instance to use
    """
    global _event_bus_instance
    _event_bus_instance = event_bus


def subscribe(
    event_name: str, handler: Optional[Callable[[Dict[str, Any]], None]] = None
) -> Any:
    """Subscribe to events with the specified name.

    Can be used as a normal function call or as a decorator.

    Args:
        event_name: The name of the event to subscribe to
        handler: Optional, the function to call when the event is published
                 Not needed when used as a decorator

    Returns:
        When used as a decorator, returns the decorated function; otherwise None
    """
    # Case when used as a decorator
    if handler is None:

        def decorator(func: handler_type) -> handler_type:
            _get_event_bus().subscribe(event_name, func)
            return func

        return decorator

    # Case when used as a normal function call
    _get_event_bus().subscribe(event_name, handler)


def unsubscribe(
    event_name: str, handler: Optional[Callable[[Dict[str, Any]], None]] = None
):
    """Unsubscribe from events with the specified name.

    Args:
        event_name: The name of the event to unsubscribe from
        handler: Optional, the specific handler to unsubscribe. If not provided,
                 all handlers for the event will be unsubscribed.
    """
    _get_event_bus().unsubscribe(event_name, handler)


def publish(event):
    """Publish an event.

    Args:
        event: The event object to publish
    """
    _get_event_bus().publish(event)


# Alias for backward compatibility
def subscript(event_name: str, handler):
    """Subscribe method (for backward compatibility)"""
    subscribe(event_name, handler)


# Export the main classes and functions
__all__ = [
    "RedisEventBus",
    "subscribe",
    "unsubscribe",
    "publish",
    "subscript",
    "set_event_bus",
    "_get_event_bus",
]
