import aio_pika
import logging
import json
from app.sql.database import SessionLocal # pylint: disable=import-outside-toplevel
from app.sql import crud, models


logger = logging.getLogger(__name__)

async def subscribe_channel(type, ex_name: str):
    # Define your RabbitMQ server connection parameters directly as keyword arguments
    connection = await aio_pika.connect_robust(
        host='rabbitmq',
        port=5672,
        virtualhost='/',
        login='guest',
        password='guest'
    )
    # Create a channel
    global channel
    channel = await connection.channel()
    # Declare the exchange
    global exchange_name
    exchange_name = ex_name
    global exchange
    exchange = await channel.declare_exchange(name=exchange_name, type=type, durable=True)


async def on_log_message(message):
    async with message.process():
        logger.info(f" [x] Received message from {exchange_name}: {message.body.decode()}")
        print(f" [x] Received message from {exchange_name}: {message.body.decode()}")
        routing_key = message.routing_key
        data = message.body
        log = models.Log(
            exchange=exchange_name,
            routing_key=routing_key,
            data=data
        )
        db = SessionLocal()
        log = await crud.create_log(db, log)
        print(log)
        await db.close()

async def subscribe_logs(queue_name: str):
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "logs.#"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)

    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_log_message(message)
