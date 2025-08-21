"""Basic Usage Example

This example demonstrates how to use the Eve Bus library for basic event publishing and subscription.
"""

import logging
import time
from redis import Redis
from eve.adapters.events import (
    RedisEventBus,
    subscribe,
    publish,
    set_event_bus,
    unsubscribe,
)
from eve.domain.events import Event

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


# Define a custom event class
class UserCreated(Event):
    user_id: str
    username: str
    email: str


class OrderPlaced(Event):
    order_id: str
    user_id: str
    items: list
    total_amount: float


# Define event handlers
@subscribe("UserCreated")
def handle_user_created(event_data):
    print(f"New user created: {event_data['username']} ({event_data['email']})")
    # Simulate some processing
    time.sleep(0.5)
    print(f"User {event_data['user_id']} registration completed")


@subscribe("OrderPlaced")
def handle_order_placed(event_data):
    print(f"New order placed by user {event_data['user_id']}")
    print(f"Order ID: {event_data['order_id']}")
    print(f"Items: {event_data['items']}")
    print(f"Total amount: ${event_data['total_amount']}")
    # Simulate some processing
    time.sleep(0.5)
    print(f"Order {event_data['order_id']} processed")


# Another handler for the same event
@subscribe("OrderPlaced")
def handle_order_notification(event_data):
    print(f"Sending notification for order {event_data['order_id']}")
    # Simulate notification sending
    time.sleep(0.2)
    print(f"Notification for order {event_data['order_id']} sent")


# Direct function subscription example
def handle_user_activity(event_data):
    print(
        f"User activity recorded: {event_data['activity_type']} by user {event_data['user_id']}"
    )


# Define another event
class UserActivity(Event):
    user_id: str
    activity_type: str
    timestamp: float


def main():
    # Create a Redis client
    redis_client = Redis(host="localhost", port=6379, db=0)

    # Create an event bus instance (optional, as the library will create a default one)
    event_bus = RedisEventBus(redis_client)

    # Set the custom event bus instance (optional)
    set_event_bus(event_bus)

    # Subscribe using the function directly
    subscribe("UserActivity", handle_user_activity)

    print("Event bus initialized. Publishing events...")

    # Publish events
    user_created_event = UserCreated(
        user_id="123", username="john_doe", email="john@example.com"
    )
    publish(user_created_event)

    # Wait a bit to ensure the event is processed
    time.sleep(1)

    order_placed_event = OrderPlaced(
        order_id="ORD-001",
        user_id="123",
        items=[
            {"product_id": "P001", "name": "Product 1", "quantity": 2, "price": 19.99},
            {"product_id": "P002", "name": "Product 2", "quantity": 1, "price": 29.99},
        ],
        total_amount=69.97,
    )
    publish(order_placed_event)

    # Wait a bit to ensure the event is processed
    time.sleep(1)

    user_activity_event = UserActivity(
        user_id="123", activity_type="login", timestamp=time.time()
    )
    publish(user_activity_event)

    # Wait a bit before shutting down
    time.sleep(1)

    # Unsubscribe from an event
    unsubscribe("UserActivity", handle_user_activity)
    print("Unsubscribed from UserActivity events")

    # Try publishing another UserActivity event (should not be processed)
    another_activity_event = UserActivity(
        user_id="123", activity_type="logout", timestamp=time.time()
    )
    publish(another_activity_event)

    # Wait a bit before shutting down
    time.sleep(1)

    # Shutdown the event bus when done
    print("Shutting down event bus...")
    event_bus.shutdown()
    print("Example completed")


import sys

if __name__ == "__main__":
    try:
        main()
    finally:
        # Force exit the program to ensure it doesn't hang
        # This is a last resort to handle any lingering background threads
        print("Forcing program exit to ensure clean termination")
        sys.exit(0)
