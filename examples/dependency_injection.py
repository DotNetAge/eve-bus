"""Dependency Injection Example

This example demonstrates how to integrate the Eve Bus with a dependency injection framework.
"""
import logging
import time
from dependency_injector import containers, providers
from redis import Redis
from eve.adapters.events import RedisEventBus, subscribe, publish, set_event_bus
from eve.domain.events import Event

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


# Define custom events
class ProductCreated(Event):
    product_id: str
    name: str
    price: float


class InventoryUpdated(Event):
    product_id: str
    quantity: int


# Define a service that publishes events
class ProductService:
    def __init__(self, event_bus: RedisEventBus):
        self.event_bus = event_bus
    
    def create_product(self, product_id: str, name: str, price: float):
        # Create product logic would go here
        print(f"Creating product: {name} (ID: {product_id}) with price ${price}")
        
        # Publish the product created event
        event = ProductCreated(product_id=product_id, name=name, price=price)
        self.event_bus.publish(event)
        
        return {"product_id": product_id, "name": name, "price": price}


# Define a service that subscribes to events
class InventoryService:
    def __init__(self):
        # Subscribe to events in the constructor
        subscribe('ProductCreated', self.handle_product_created)
    
    def handle_product_created(self, event_data):
        print(f"Initializing inventory for new product: {event_data['name']}")
        # Simulate inventory initialization
        time.sleep(0.5)
        
        # Publish inventory updated event
        inventory_event = InventoryUpdated(
            product_id=event_data['product_id'],
            quantity=100  # Initial quantity
        )
        publish(inventory_event)
        
        print(f"Inventory initialized for product {event_data['product_id']}")
    
    def handle_inventory_updated(self, event_data):
        print(f"Inventory updated for product {event_data['product_id']}: new quantity is {event_data['quantity']}")
        # Here you would update the inventory records


# Define a dependency injection container
class AppContainer(containers.DeclarativeContainer):
    # Configuration
    config = providers.Configuration()
    
    # Redis client provider
    redis_client = providers.Singleton(
        Redis,
        host=config.redis.host,
        port=config.redis.port,
        db=config.redis.db,
        password=config.redis.password,
        decode_responses=True
    )
    
    # Event bus provider
    event_bus = providers.Singleton(
        RedisEventBus,
        redis_client=redis_client
    )
    
    # Service providers
    product_service = providers.Factory(
        ProductService,
        event_bus=event_bus
    )
    
    inventory_service = providers.Factory(
        InventoryService
    )


# Define a handler that uses container services
class OrderService:
    def __init__(self, container: AppContainer):
        self.container = container
        # Subscribe to events using container services
        subscribe('InventoryUpdated', self.handle_inventory_updated)
    
    def handle_inventory_updated(self, event_data):
        print(f"Order service notified of inventory update for product {event_data['product_id']}")
        # Here you might check if there are pending orders that can be fulfilled
        inventory_service = self.container.inventory_service()
        inventory_service.handle_inventory_updated(event_data)


# Create a function to demonstrate the setup

def main():
    # Create and configure the container
    container = AppContainer()
    container.config.redis.host.from_value('localhost')
    container.config.redis.port.from_value(6379)
    container.config.redis.db.from_value(0)
    container.config.redis.password.from_value(None)
    
    # Set the event bus instance from the container
    set_event_bus(container.event_bus())
    
    # Create services
    product_service = container.product_service()
    inventory_service = container.inventory_service()
    order_service = OrderService(container)
    
    print("Application initialized with dependency injection. Creating a product...")
    
    # Create a product, which will trigger the event chain
    product = product_service.create_product(
        product_id='PROD-001',
        name='Premium Widget',
        price=49.99
    )
    
    print(f"Product created successfully: {product}")
    
    # Wait for all events to be processed
    time.sleep(2)
    
    # Create another product to see the event chain again
    product2 = product_service.create_product(
        product_id='PROD-002',
        name='Superior Gadget',
        price=79.99
    )
    
    print(f"Second product created successfully: {product2}")
    
    # Wait for all events to be processed
    time.sleep(2)
    
    # Shutdown the event bus when done
    print("Shutting down event bus...")
    container.event_bus().shutdown()
    print("Dependency injection example completed")


if __name__ == '__main__':
    main()