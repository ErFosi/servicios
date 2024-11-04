import aio_pika
import json
from app.sql.database import SessionLocal # pylint: disable=import-outside-toplevel

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

    global exchange_logs_name
    exchange_logs_name = 'exchange'
    global exchange_logs
    exchange_logs = await channel.declare_exchange(name=exchange_logs_name, type='topic', durable=True)


async def publish_log(message_body, routing_key):
    # Publish the message to the exchange
    await exchange_logs.publish(
        aio_pika.Message(
            body=message_body.encode(),
            content_type="text/plain"
        ),
        routing_key=routing_key)