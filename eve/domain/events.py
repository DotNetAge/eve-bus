"""Domain Events

This module defines the base Event class and common event types.
"""
from pydantic import BaseModel, ConfigDict
from typing import List, Dict, Any


class Event(BaseModel):
    """Base event class for all domain events.
    
    All domain events should inherit from this class.
    """
    
    model_config = ConfigDict(from_attributes=True)

    @property
    def name(self) -> str:
        """Get the event name."""
        return self.__class__.__name__

    def model_dump_json(self, **kwargs) -> str:
        """Convert the event to a JSON string."""
        # Override if needed for custom serialization
        return super().model_dump_json(**kwargs)

    @classmethod
    def model_validate_json(cls, json_data: str) -> "Event":
        """Create an event from a JSON string."""
        # Override if needed for custom deserialization
        return super().model_validate_json(json_data)


# Common event types can be defined here
class EntityCreated(Event):
    """Generic entity created event."""
    entity_id: str
    entity_type: str
    data: Dict[str, Any]


class EntityUpdated(Event):
    """Generic entity updated event."""
    entity_id: str
    entity_type: str
    changes: Dict[str, Any]


class EntityDeleted(Event):
    """Generic entity deleted event."""
    entity_id: str
    entity_type: str


class TaskCompleted(Event):
    """Task completed event."""
    task_id: str
    result: Dict[str, Any] = {}


class TaskFailed(Event):
    """Task failed event."""
    task_id: str
    error_message: str
    details: Dict[str, Any] = {}


class SystemStatusChanged(Event):
    """System status changed event."""
    component: str
    status: str  # e.g., 'online', 'offline', 'degraded'
    message: str = ""