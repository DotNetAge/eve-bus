"""Event Ports

This module defines the abstract interfaces for event publishing and subscription.
"""
from abc import ABC, abstractmethod
from typing import Callable, Dict, Any, Optional
from eve.domain.events import Event


class EventPublisherPort(ABC):
    """Domain event publisher port.
    
    This interface defines the contract for publishing domain events.
    """

    @abstractmethod
    def publish(self, event: Event):
        """Publish a domain event.

        Args:
            event: The event object to publish
        """
        ...


class EventSubscriberPort(ABC):
    """Domain event subscriber port.
    
    This interface defines the contract for subscribing to domain events.
    """

    @abstractmethod
    def subscribe(self, event_name: str, handler: Callable[[Dict[str, Any]], None]):
        """Subscribe to events with the specified name.

        Args:
            event_name: The name of the event to subscribe to
            handler: The function to call when the event is published
        """
        ...

    @abstractmethod
    def unsubscribe(self, event_name: str, handler: Optional[Callable[[Dict[str, Any]], None]] = None):
        """Unsubscribe from events with the specified name.

        Args:
            event_name: The name of the event to unsubscribe from
            handler: Optional, the specific handler to unsubscribe. If not provided,
                     all handlers for the event will be unsubscribed.
        """
        ...