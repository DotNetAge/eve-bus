# Eve Bus

A lightweight, reliable event bus implementation using Redis as the message broker. This library provides a simple interface for publishing and subscribing to events in distributed systems, enabling efficient communication between components in microservice architectures.

## Features

- **Simple yet powerful API**: Intuitive interface for publishing and subscribing to events
- **Redis-backed**: Leverages Redis' pub/sub functionality for robust message delivery
- **Thread-safe implementation**: Safe for use in multi-threaded environments
- **Multiple handlers per event**: Support for registering multiple functions to handle the same event
- **Automatic retry mechanism**: Built-in support for retrying failed event handlers
- **Clean shutdown**: Proper resource management and graceful shutdown
- **Dependency injection ready**: Easy integration with popular DI frameworks
- **Distributed system friendly**: Ideal for communication between services in microservice architectures
- **Type-safe events**: Leverages Python's type hinting for event data structures
- **Minimal dependencies**: Lightweight with few external dependencies

## Architecture Highlights

Eve Bus follows a clean architecture approach with clear separation of concerns:

- **Domain layer**: Defines core event models
- **Ports layer**: Specifies abstract interfaces for event publishing and subscription
- **Adapters layer**: Implements the ports using Redis as the underlying technology

This architecture ensures loose coupling between your application code and the event bus implementation, making it easy to swap out the underlying message broker if needed.

## Installation

```bash
pip install eve-bus
```

## Usage

### Basic Setup

```python
from redis import Redis
from eve.adapters.events import RedisEventBus, subscribe, publish, set_event_bus
from eve.domain.events import Event

# Create a Redis client
redis_client = Redis(host='localhost', port=6379, db=0)

# Create an event bus instance
event_bus = RedisEventBus(redis_client)

# Set the global event bus instance (required for using @subscribe decorator)
set_event_bus(event_bus)

# Define an event class
class UserCreated(Event):
    user_id: str
    username: str
    email: str

# Subscribe to an event
@subscribe('UserCreated')
def handle_user_created(event_data):
    print(f"New user created: {event_data['username']} ({event_data['email']})")
    print(f"User ID: {event_data['user_id']}")

# Publish an event
user_created_event = UserCreated(user_id='123', username='john_doe', email='john@example.com')
publish(user_created_event)

# When done, shutdown the event bus to clean up resources
event_bus.shutdown()
```

### Using with Dependency Injection

Eve Bus integrates seamlessly with dependency injection frameworks like `dependency_injector`:

```python
from dependency_injector import containers, providers
from redis import Redis
from eve.adapters.events import RedisEventBus, subscribe, set_event_bus
from eve.domain.events import Event

class Container(containers.DeclarativeContainer):
    # Redis client provider
    redis_client = providers.Singleton(
        Redis,
        host='localhost',
        port=6379,
        db=0
    )

    # Event bus provider
    event_bus = providers.Singleton(RedisEventBus, redis_client=redis_client)

# Define a service that uses the event bus
class UserService:
    def __init__(self, event_bus: RedisEventBus):
        self.event_bus = event_bus
    
    def create_user(self, user_id: str, username: str, email: str):
        # Create user logic here
        print(f"Creating user: {username}")
        
        # Publish user created event
        event = UserCreated(user_id=user_id, username=username, email=email)
        self.event_bus.publish(event)
        
        return {"user_id": user_id, "username": username}

# Add the service to the container
Container.user_service = providers.Factory(UserService, event_bus=Container.event_bus)

# Create a container instance
container = Container()

# Get the event bus instance and set it globally
set_event_bus(container.event_bus())

# Get the user service
user_service = container.user_service()

# Use the service
user_service.create_user("456", "jane_doe", "jane@example.com")
```

### Integration with FastAPI

Here's how to integrate Eve Bus with FastAPI:

```python
from fastapi import FastAPI, Depends, BackgroundTasks
from redis import Redis
from eve.adapters.events import RedisEventBus, subscribe, publish, set_event_bus
from eve.domain.events import Event
from pydantic import BaseModel
import uvicorn

# Define event models
class OrderCreated(Event):
    order_id: str
    user_id: str
    total_amount: float

class PaymentReceived(Event):
    payment_id: str
    order_id: str
    amount: float

# FastAPI app instance
app = FastAPI(title="Eve Bus with FastAPI")

# Redis and Event Bus setup
class EventBusManager:
    _instance: RedisEventBus = None
    
    @classmethod
    def get_event_bus(cls):
        if cls._instance is None:
            redis_client = Redis(host='localhost', port=6379, db=0)
            cls._instance = RedisEventBus(redis_client)
            set_event_bus(cls._instance)
        return cls._instance

    @classmethod
    def shutdown(cls):
        if cls._instance:
            cls._instance.shutdown()
            cls._instance = None

    # Dependency to get the event bus
    @classmethod
    def get_event_bus(cls):
        return cls._instance

# Pydantic models for API requests
class CreateOrderRequest(BaseModel):
    user_id: str
    items: list
    total_amount: float

# API endpoint to create an order
@app.post("/orders/")
async def create_order(
    request: CreateOrderRequest,
    event_bus: RedisEventBus = Depends(get_event_bus)
):
    # Generate order ID (in real app, use a proper ID generation strategy)
    order_id = f"order_{hash(request.user_id + str(request.total_amount))}"
    
    # Create and publish the order created event
    event = OrderCreated(
        order_id=order_id,
        user_id=request.user_id,
        total_amount=request.total_amount
    )
    event_bus.publish(event)
    
    return {"order_id": order_id, "status": "created"}

# API endpoint to process payment
@app.post("/payments/")
async def process_payment(
    order_id: str,
    amount: float,
    background_tasks: BackgroundTasks,
    event_bus: RedisEventBus = Depends(get_event_bus)
):
    # Process payment logic here
    payment_id = f"payment_{hash(order_id + str(amount))}"
    
    # Publish payment received event using background task
    background_tasks.add_task(
        event_bus.publish,
        PaymentReceived(payment_id=payment_id, order_id=order_id, amount=amount)
    )
    
    return {"payment_id": payment_id, "status": "processing"}

# Event handler for order creation
@subscribe("OrderCreated")
def handle_order_created(event_data):
    print(f"New order received: {event_data['order_id']}")
    print(f"User ID: {event_data['user_id']}")
    print(f"Total amount: ${event_data['total_amount']}")
    # Here you could update inventory, send notifications, etc.

# Event handler for payment processing
@subscribe("PaymentReceived")
def handle_payment_received(event_data):
    print(f"Payment received: {event_data['payment_id']}")
    print(f"For order: {event_data['order_id']}")
    print(f"Amount: ${event_data['amount']}")
    # Here you could update order status, generate invoice, etc.

# Shutdown event bus on app exit
@app.on_event("shutdown")
async def shutdown_event_bus():
    event_bus = EventBusManager.get_event_bus()
    event_bus.shutdown()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Configuration

Eve Bus can be configured using environment variables. Create a `.env` file in your project root or set these variables in your environment:

### Core Configuration

- `EVENT_CHANNEL`: Prefix for Redis channels (default: 'event')
  This prefix is used when creating Redis channels for event communication.

### Redis Configuration

- `REDIS_HOST`: Redis server hostname or IP address (default: 'localhost')
- `REDIS_PORT`: Redis server port (default: 6379)
- `REDIS_DB`: Redis database number to use (default: 0)
- `REDIS_PASSWORD`: Redis server password (optional, default: None)

### Example .env File

```env
# Eve Bus Configuration
EVENT_CHANNEL=my_app_events

# Redis Configuration
REDIS_HOST=redis.example.com
REDIS_PORT=6379
REDIS_DB=2
REDIS_PASSWORD=my_secure_password
```

For advanced usage, you can also configure the Redis client directly when creating the `RedisEventBus` instance, overriding any environment variables:

## Best Practices

When using Eve Bus in your applications, consider these best practices:

1. **Define clear event structures**: Create well-defined event classes that clearly represent the data being communicated
2. **Use meaningful event names**: Choose descriptive names for your events to make the system easier to understand
3. **Handle failures gracefully**: Implement error handling in your event handlers
4. **Keep handlers focused**: Each event handler should perform a single responsibility
5. **Monitor event processing**: Add logging to track event publishing and handling
6. **Always shutdown**: Call `event_bus.shutdown()` when your application exits to clean up resources

## Advanced Usage

### Batch Processing
Eve Bus includes support for batching events, which can improve performance in high-throughput scenarios.

### Error Handling and Retries
You can implement custom retry logic for failed event handlers to improve system resilience.

### Event Filtering
Implement event filtering to process only the events that are relevant to your application components.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.