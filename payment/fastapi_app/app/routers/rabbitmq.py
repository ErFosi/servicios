import aio_pika
import json
import ssl
from app.sql.database import SessionLocal  # pylint: disable=import-outside-toplevel
from app.sql import crud, models

with open("/keys/cert.pem", "r") as certificate:
    CERTIFICATE = certificate.read()

async def subscribe_channel():
    ssl_context = ssl.create_default_context(cadata=CERTIFICATE)

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
    # Declare the exchange

    global exchange_name
    exchange_name = 'exchange'
    global exchange_responses
    exchange_responses = await channel.declare_exchange(name=exchange_name, type='topic', durable=True)


async def on_message_payment_check(message):
    async with message.process():
        order = json.loads(message.body)
        db = SessionLocal()
        balance, status = await crud.update_balance_by_user_id(db, order['id_client'], order['movement'])
        await db.close()
        data = {
            "id_order": order['id_order'],
            "status": status
        }
        message_body = json.dumps(data)
        routing_key = "events.order.checked"
        await publish_response(message_body, routing_key)


async def subscribe_payment_check():
    # Create queue
    queue_name = "events.order.created.pending"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "events.order.created.pending"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_message_payment_check(message)


async def publish_response(message_body, routing_key):
    # Publish the message to the exchange
    await exchange_responses.publish(
        aio_pika.Message(
            body=message_body.encode(),
            content_type="text/plain"
        ),
        routing_key=routing_key)

