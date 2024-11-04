import asyncio
import aio_pika
import json
import logging
from app.sql import crud
from app.routers import rabbitmq_publish_logs

logger = logging.getLogger(__name__)


async def subscribe_channel():
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
    exchange_name = 'exchange'
    global exchange
    exchange = await channel.declare_exchange(name=exchange_name, type='topic', durable=True)


async def on_message(message):
    async with message.process():
        piece = json.loads(message.body)
        await crud.set_status_of_machine("Machine Status: Producing")
        await asyncio.sleep(3)
        data = {
            "id_piece": piece['piece_id'],
            "id_order": piece['order_id']
        }
        message_body = json.dumps(data)
        routing_key = "events.piece.produced"
        await publish(message_body, routing_key)
        data = {
            "message": "INFO - Estado de la pieza" + str(piece['piece_id']) + "del Order " + str(piece['order_id']) + "cambiado a producido correctamente"
        }
        message_body = json.dumps(data)
        routing_key = "logs.info.machine"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)


async def subscribe():
    # Create queue
    queue_name = "events.piece.created"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "events.piece.created"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_message(message)


async def publish(message_body, routing_key):
    logger.info("Intentando publicar mensaje con routing_key: %s", routing_key)
    await exchange.publish(
        aio_pika.Message(
            body=message_body.encode(),
            content_type="text/plain"
        ),
        routing_key=routing_key
    )
    logger.info("Mensaje publicado con éxito")

