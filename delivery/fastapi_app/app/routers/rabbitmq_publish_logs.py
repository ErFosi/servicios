import aio_pika
import logging
import json
from app.sql.database import SessionLocal # pylint: disable=import-outside-toplevel

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

    global exchange_logs_name
    exchange_logs_name = 'exchange'
    global exchange_logs
    exchange_logs = await channel.declare_exchange(name=exchange_logs_name, type=type, durable=True)

async def formato_log_message(level: str, message: str):

    if level == "debug":
        logger.debug(message)
    elif level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)

    routing_key = f"logs.{level}.delivery"
    return message, routing_key

async def publish_log(message_body, routing_key):
    # Publish the message to the exchange
    await exchange_logs.publish(
        aio_pika.Message(
            body=message_body.encode(),
            content_type="text/plain"
        ),
        routing_key=routing_key)

    print(f"Log enviado a RabbitMQ: {routing_key}")
    logger.debug(f"Log enviado a RabbitMQ: {routing_key}")
