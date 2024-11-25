import aio_pika
import json
import ssl
from app.sql.database import SessionLocal # pylint: disable=import-outside-toplevel


ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

async def subscribe_channel():
    connection = await aio_pika.connect_robust(
        host='rabbitmq',
        port=5671,
        virtualhost='/',
        login='guest',
        password='guest',
        ssl_options=aio_pika.SSLOptions(context=ssl_context)
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