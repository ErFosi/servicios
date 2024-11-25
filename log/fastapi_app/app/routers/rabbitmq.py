import aio_pika
import logging
import json
from app.sql.database import SessionLocal # pylint: disable=import-outside-toplevel
from app.sql import crud, models
import ssl

logger = logging.getLogger(__name__)


async def subscribe_channel(type, ex_name: str):

    connection = await aio_pika.connect_robust(
        host='rabbitmq',
        port=5671,
        virtualhost='/',
        login='guest',
        password='guest',
        ssl=True
    )
    # Create a channel
    global channel
    channel = await connection.channel()
    # Declare the exchange
    global exchange_commands_name
    exchange_commands_name = 'commands'
    global exchange_commands
    exchange_commands = await channel.declare_exchange(name=exchange_commands_name, type=type, durable=True)

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

async def on_command_log_message(message):
    async with message.process():
        log = models.Log(
            #exchange=message.exchange,
            exchange=exchange_commands_name,
            routing_key=message.routing_key,
            data=message.body
        )
        db = SessionLocal()
        await crud.create_log(db, log)
        await db.close()


async def subscribe_commands_logs():
    # Create a queue
    queue_name = "commands_logs"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "#"
    await queue.bind(exchange=exchange_commands, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_command_log_message(message)
