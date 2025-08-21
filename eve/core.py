"""Bus Module

Provides event publishing and subscription functionality with Redis as the message broker.
"""

from typing import Callable, Dict, Any, Optional, TypeVar
import logging
import os
from abc import ABC, abstractmethod
from dotenv import load_dotenv
import redis
from redis.client import PubSub
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from collections import defaultdict
import json
from pydantic import BaseModel, ConfigDict

load_dotenv()

logger = logging.getLogger(__name__)

# Generic type for type annotation
handler_type = TypeVar("handler_type", bound=Callable[[Dict[str, Any]], None])


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
    def unsubscribe(
        self,
        event_name: str,
        handler: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """Unsubscribe from events with the specified name.

        Args:
            event_name: The name of the event to unsubscribe from
            handler: Optional, the specific handler to unsubscribe. If not provided,
                     all handlers for the event will be unsubscribed.
        """
        ...


class RedisEventBus(EventSubscriberPort, EventPublisherPort):
    """Redis-based event bus implementation.

    Implements event publishing and subscription functionality using Redis as a message broker,
    with support for multi-threaded event processing.
    """

    def __init__(self, redis_client: redis.Redis):
        """Initialize the Redis event bus.

        Args:
            redis_client: Redis client instance
        """
        self.redis_client = redis_client
        self.event_handlers = defaultdict(list)  # Store event handlers
        self.handler_lock = Lock()  # Lock to protect the event handlers list
        self.active_pubsubs = {}  # Store active PubSub objects
        self.pubsub_lock = Lock()  # Lock to protect PubSub objects
        self.event_queue = defaultdict(list)  # Event queue for batch processing
        self.event_queue_lock = Lock()  # Lock to protect the event queue
        self.processing_scheduled = defaultdict(
            bool
        )  # Track if processing is scheduled
        self.processing_scheduled_lock = Lock()  # Lock to protect processing_scheduled
        self._shutdown_flag = False  # Flag to indicate if shutdown is in progress
        self._shutdown_lock = Lock()  # Lock to protect the shutdown flag

        # Create a thread pool for event processing
        self.executor = ThreadPoolExecutor(
            max_workers=10, thread_name_prefix="event-listener"
        )

        # Channel prefix, obtained from configuration
        self.channel_prefix = os.getenv("EVENT_CHANNEL", "events")
        # Special channel for internal control messages
        self.control_channel = f"{self.channel_prefix}:__control__"

    def subscribe(self, event_name: str, handler: Callable[[Dict[str, Any]], None]):
        """Subscribe to events with the specified name.

        Args:
            event_name: The name of the event to subscribe to
            handler: The function to call when the event is published
        """
        with self.handler_lock:
            if handler not in self.event_handlers[event_name]:
                self.event_handlers[event_name].append(handler)
                logger.info(f"Subscribed to event: {event_name}")

                # Start listening only on the first subscription
                if len(self.event_handlers[event_name]) == 1:
                    self._start_listener(event_name)

    def unsubscribe(
        self,
        event_name: str,
        handler: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """Unsubscribe from events with the specified name.

        Args:
            event_name: The name of the event to unsubscribe from
            handler: Optional, the specific handler to unsubscribe. If not provided,
                     all handlers for the event will be unsubscribed.
        """
        with self.handler_lock:
            if handler:
                # Unsubscribe a specific handler
                if handler in self.event_handlers[event_name]:
                    self.event_handlers[event_name].remove(handler)
                    logger.info(
                        f"Unsubscribed specific handler from event: {event_name}"
                    )
            else:
                # Unsubscribe all handlers
                self.event_handlers[event_name] = []
                logger.info(f"Unsubscribed all handlers from event: {event_name}")

            # Stop listening if there are no handlers left
            if not self.event_handlers[event_name]:
                self._stop_listener(event_name)

    def publish(self, event: Event):
        """Publish an event.

        Args:
            event: The event object to publish
        """
        try:
            # Serialize the event to JSON string
            event_json = event.model_dump_json()
            # Use hex encoding to ensure safe transmission
            encoded_event = event_json.encode().hex()

            # Publish to the corresponding channel
            channel = f"{self.channel_prefix}:{event.name}"
            self.redis_client.publish(channel, encoded_event)
            logger.info(f"Published event: {event.name} to channel: {channel}")
        except Exception as e:
            logger.error(f"Failed to publish event: {event.name}, error: {e}")

    def _start_listener(self, event_name: str):
        """Start an event listening thread.

        Args:
            event_name: The name of the event to listen for
        """
        try:
            # Create a PubSub object
            pubsub = self.redis_client.pubsub()
            channel = f"{self.channel_prefix}:{event_name}"
            pubsub.subscribe(channel)

            # Store the PubSub object
            with self.pubsub_lock:
                self.active_pubsubs[event_name] = pubsub

            logger.info(f"Started listener thread: {channel}")

            # Start the listener using the thread pool
            self.executor.submit(self._listen, event_name, pubsub)
        except Exception as e:
            logger.error(f"Failed to start listener: {event_name}, error: {e}")

    def _stop_listener(self, event_name: str):
        """Stop an event listening thread.

        Args:
            event_name: The name of the event to stop listening for
        """
        with self.pubsub_lock:
            if event_name in self.active_pubsubs:
                pubsub = self.active_pubsubs.pop(event_name)
                try:
                    channel = f"{self.channel_prefix}:{event_name}"
                    # Check if pubsub is not None and still valid before calling methods
                    if pubsub is not None:
                        try:
                            pubsub.unsubscribe(channel)
                        except Exception:
                            # Ignore unsubscribe errors if already unsubscribed
                            pass
                        try:
                            pubsub.close()
                        except Exception:
                            # Ignore close errors if already closed
                            pass
                        logger.info(f"Stopped listener thread: {channel}")
                except Exception as e:
                    logger.error(f"Failed to stop listener: {event_name}, error: {e}")

    def _listen(self, event_name: str, pubsub: PubSub):
        """Internal method to listen for events.

        Args:
            event_name: The name of the event to listen for
            pubsub: Redis PubSub object
        """
        # Also subscribe to the control channel for shutdown messages
        control_channel = self.control_channel
        try:
            pubsub.subscribe(control_channel)
        except Exception as e:
            logger.warning(f"Failed to subscribe to control channel: {e}")

        try:
            # Use a timeout to allow checking shutdown flag periodically
            pubsub.timeout = 1.0  # 1 second timeout

            for item in pubsub.listen():
                # Check if shutdown is in progress
                with self._shutdown_lock:
                    if self._shutdown_flag:
                        logger.info(f"Listener detected shutdown signal: {event_name}")
                        break

                # Check for control messages
                if item.get("type") == "message":
                    channel = (
                        item.get("channel", b"").decode("utf-8")
                        if isinstance(item.get("channel"), bytes)
                        else item.get("channel", "")
                    )
                    if channel == control_channel:
                        data = (
                            item.get("data", b"").decode("utf-8")
                            if isinstance(item.get("data"), bytes)
                            else item.get("data", "")
                        )
                        if data == "shutdown":
                            logger.info(
                                f"Listener received shutdown control message: {event_name}"
                            )
                            break
                try:
                    if item["type"] == "message":
                        # Check if the event listener is still active
                        with self.handler_lock:
                            if not self.event_handlers.get(event_name, []):
                                break

                        # Parse the event
                        try:
                            # Initialize variables to avoid UnboundLocalError
                            event = None
                            event_str = ""

                            # Extract the event name from the channel
                            # The channel is in format: channel_prefix:event_name
                            channel_parts = (
                                item["channel"].decode("utf-8").split(":")
                                if isinstance(item["channel"], bytes)
                                else item["channel"].split(":")
                            )
                            if len(channel_parts) >= 2:
                                actual_event_name = channel_parts[1]
                            else:
                                actual_event_name = "Event"

                            # Check if data is bytes or string
                            if isinstance(item["data"], bytes):
                                try:
                                    # First decode from bytes to string
                                    data_str = item["data"].decode("utf-8")
                                    # Then decode from hex to get the original JSON string
                                    event_str = bytes.fromhex(data_str).decode("utf-8")
                                except Exception as e:
                                    logger.error(f"Failed to decode event data: {e}")
                                    logger.error(f"Raw data: {item['data']}")
                                    continue
                            else:
                                try:
                                    # If data is string, it's already hex encoded
                                    # Decode from hex to get the original JSON string
                                    event_str = bytes.fromhex(item["data"]).decode(
                                        "utf-8"
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to decode event data: {e}")
                                    logger.error(f"Raw data: {item['data']}")
                                    continue

                            # Now try to decode the event with the correct type
                            try:
                                import json

                                event_data = json.loads(event_str)

                                # Try to find the specific event class by name
                                from eve.domain.events import Event

                                found_specific_class = False

                                # Get all subclasses of Event including nested ones
                                all_subclasses = []

                                def get_all_subclasses(cls):
                                    for subclass in cls.__subclasses__():
                                        all_subclasses.append(subclass)
                                        get_all_subclasses(subclass)

                                get_all_subclasses(Event)

                                # Try to find a matching subclass
                                for subclass in all_subclasses:
                                    if subclass.__name__ == actual_event_name:
                                        event = subclass(**event_data)
                                        found_specific_class = True
                                        break

                                # If no specific class found, use base Event class
                                if not found_specific_class:
                                    event = Event.model_validate_json(event_str)
                            except Exception as e:
                                logger.error(f"Failed to parse event data: {e}")
                                logger.error(f"Event data: {event_str}")
                                continue

                            if event:
                                logger.info(
                                    f"Successfully decoded event: {actual_event_name}"
                                )
                                # Add the event to the queue for batch processing only if it's valid
                                self._queue_event(event)
                            else:
                                logger.warning(
                                    "Received event is None after decoding attempt"
                                )
                        except Exception as e:
                            logger.error(f"Failed to parse event: {e}")
                            logger.error(f"Raw data: {item['data']}")
                except Exception as e:
                    logger.error(f"Failed to process message: {e}")
        except Exception as e:
            # Check if the error is due to PubSub being closed normally
            error_msg = str(e)
            if (
                "I/O operation on closed file" in error_msg
                or "connection pool is closed" in error_msg
            ):
                # This is an expected error when the listener is intentionally stopped
                logger.debug(f"Listener stopped normally: {event_name}")
            else:
                logger.error(f"Listener exited abnormally: {event_name}, error: {e}")
                # Check if the listener needs to be restarted
                with self.handler_lock:
                    if self.event_handlers.get(event_name, []):
                        logger.info(f"Attempting to restart listener: {event_name}")
                        # Restart the listener after a delay to avoid immediate retry resource waste
                        import time

                        time.sleep(1)
                        self._start_listener(event_name)
        finally:
            # Ensure the PubSub object is properly cleaned up
            try:
                pubsub.close()
                with self.pubsub_lock:
                    if event_name in self.active_pubsubs:
                        del self.active_pubsubs[event_name]
            except Exception as e:
                logger.error(
                    f"Failed to clean up PubSub object: {event_name}, error: {str(e)}"
                )

    def _queue_event(self, event: Event):
        """Queue an event for batch processing.

        Args:
            event: The event object to queue
        """
        logger.info(f"Queuing event for processing: {event.name}")
        # Parse event arguments
        args_obj = None
        try:
            # Try to convert the entire event to a dictionary
            args_obj = event.model_dump()
            logger.debug(f"Successfully parsed event arguments for {event.name}")
        except Exception as e:
            logger.error(f"Failed to parse event arguments: {e}")
            logger.error(f"Event: {event}")

        # Add the event to the queue
        with self.event_queue_lock:
            self.event_queue[event.name].append((event, args_obj))
            logger.debug(
                f"Event {event.name} added to queue. Queue size: {len(self.event_queue[event.name])}"
            )

        # Schedule event processing
        with self.processing_scheduled_lock:
            if not self.processing_scheduled[event.name]:
                self.processing_scheduled[event.name] = True
                logger.debug(f"Scheduling processing for event queue: {event.name}")
                self.executor.submit(self._process_event_queue, event.name)

    def _process_event_queue(self, event_name: str):
        """Process events in the event queue.

        Args:
            event_name: The name of the event to process
        """
        logger.info(f"Starting processing for event queue: {event_name}")
        # Reset the processing scheduled flag
        with self.processing_scheduled_lock:
            self.processing_scheduled[event_name] = False

        # Get the current event queue and handler list
        events_to_process = []
        handlers = []

        with self.event_queue_lock:
            events_to_process = self.event_queue[event_name].copy()
            self.event_queue[event_name] = []
            logger.debug(
                f"Retrieved {len(events_to_process)} events from queue for {event_name}"
            )

        with self.handler_lock:
            handlers = self.event_handlers.get(event_name, []).copy()
            logger.debug(f"Found {len(handlers)} handlers registered for {event_name}")

        # Process all events
        for event, args_obj in events_to_process:
            # Execute all handlers for each event
            for handler in handlers:
                max_retries = 3  # Maximum number of retries
                retry_count = 0
                success = False

                while retry_count < max_retries and not success:
                    try:
                        handler(args_obj)
                        success = True
                    except Exception as e:
                        retry_count += 1
                        if retry_count >= max_retries:
                            logger.error(
                                f"Handler {handler.__name__ if hasattr(handler, '__name__') else str(handler)} failed to process event, reached maximum retries ({max_retries}): {str(e)}"
                            )
                            logger.error(f"Event: {event_name}, Event args: {args_obj}")
                        else:
                            logger.warning(
                                f"Handler {handler.__name__ if hasattr(handler, '__name__') else str(handler)} failed to process event, will retry in {0.5 * retry_count} seconds ({retry_count}/{max_retries}): {str(e)}"
                            )
                            # Exponential backoff strategy
                            import time

                            time.sleep(0.5 * retry_count)
                            # If there are still events in the queue, don't block the main thread from processing other events
                            if self.event_queue[event_name]:
                                # Re-add the failed event to the queue for later processing
                                with self.event_queue_lock:
                                    self.event_queue[event_name].append(
                                        (event, args_obj)
                                    )
                                # Ensure processing is scheduled
                                with self.processing_scheduled_lock:
                                    if not self.processing_scheduled[event_name]:
                                        self.processing_scheduled[event_name] = True
                                        self.executor.submit(
                                            self._process_event_queue, event_name
                                        )
                                break  # Exit the retry loop to process the next event

    def _parse_json(self, s: str) -> Optional[Dict[str, Any]]:
        """Parse a JSON string.

        Args:
            s: JSON string

        Returns:
            Parsed dictionary, or None if parsing fails
        """
        if s is None or s == "":
            return None
        try:
            return json.loads(s)
        except json.JSONDecodeError as e:
            logger.error(
                f"JSON parsing failed: {str(e)}. Error position: {e.pos}, Line: {e.lineno}, Column: {e.colno}"
            )
            logger.error(
                f"Raw JSON data: {s[:100]}{'...' if len(s) > 100 else ''}"
            )  # Limit log size
            return None
        except Exception as e:
            logger.error(f"Unexpected error when parsing string: {str(e)}")
            return None

    def shutdown(self, timeout=2.0):
        """Shut down the event bus and clean up resources.

        Args:
            timeout: Maximum time to wait for resources to be released (in seconds)
        """
        logger.info(f"Initiating event bus shutdown sequence with timeout={timeout}s")

        # Set the shutdown flag first
        with self._shutdown_lock:
            self._shutdown_flag = True

        # Publish a control message to wake up all blocking listeners
        try:
            control_channel = self.control_channel
            self.redis_client.publish(control_channel, "shutdown")
            logger.info(
                f"Published shutdown control message to channel: {control_channel}"
            )
        except Exception as e:
            logger.warning(f"Failed to publish shutdown control message: {e}")

        # Stop all listeners
        with self.pubsub_lock:
            event_names = list(self.active_pubsubs.keys())
            logger.info(f"Stopping {len(event_names)} active listeners")
            for event_name in event_names:
                self._stop_listener(event_name)

        # Give a short time for listeners to process the shutdown message
        time.sleep(min(0.2, timeout))

        # Force close Redis connection to ensure all threads are interrupted
        try:
            # Forcefully close the Redis connection pool - this is crucial for interrupting blocking calls
            if hasattr(self.redis_client, "connection_pool"):
                # Use a more aggressive approach to disconnect
                for (
                    connection
                ) in self.redis_client.connection_pool._available_connections:
                    try:
                        connection.disconnect()
                    except:
                        pass
                self.redis_client.connection_pool.disconnect()
                logger.info("Redis connection pool aggressively disconnected")
            # Explicitly close the client
            self.redis_client.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Failed to close Redis connection: {e}")

        # Shutdown the thread pool with forceful termination and timeout
        try:
            # Import necessary modules
            import threading
            import time
            import sys
            import gc

            # Create a timer to ensure we don't wait too long
            def force_shutdown():
                logger.warning("Forcing thread pool shutdown due to timeout")
                # This is a last resort - clear all references to help garbage collection
                try:
                    if hasattr(self.executor, "_threads"):
                        # Mark threads as daemon to allow interpreter to exit
                        for thread in list(self.executor._threads):
                            if thread.is_alive():
                                logger.warning(
                                    f"Marking thread as daemon: {thread.name}"
                                )
                                thread.daemon = True  # This allows Python to exit even if thread is running
                except Exception as e:
                    logger.error(f"Error during force shutdown: {e}")

            # Start the timer
            timer = threading.Timer(timeout, force_shutdown)
            timer.daemon = True
            timer.start()

            # Try to shutdown normally with cancel_futures=True and reduced wait time
            self.executor.shutdown(
                wait=False, cancel_futures=True
            )  # Set wait=False to prevent blocking

            # Give a brief moment for threads to terminate gracefully
            time.sleep(min(0.5, timeout))

            # Cancel the timer if we're done
            timer.cancel()
            logger.info(
                "Event bus thread pool has been shut down with non-blocking termination"
            )
        except Exception as e:
            logger.error(f"Failed to shutdown thread pool: {e}")

        # Additional cleanup to ensure all resources are released
        try:
            # Explicitly clear references to help garbage collection
            with self.handler_lock:
                self.event_handlers.clear()
            with self.pubsub_lock:
                self.active_pubsubs.clear()
            with self.event_queue_lock:
                self.event_queue.clear()
            with self.processing_scheduled_lock:
                self.processing_scheduled.clear()

            # Force garbage collection to clean up any remaining references
            gc.collect()
            logger.info("Event bus resources cleared and garbage collected")
        except Exception as e:
            logger.error(f"Failed to clear event bus resources: {e}")

        logger.info("Event bus has been shut down completely")


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
    "Event",
]
