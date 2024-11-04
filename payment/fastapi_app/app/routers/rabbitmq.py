import aio_pika
import json
from app.sql.database import SessionLocal  # pylint: disable=import-outside-toplevel
from app.sql import crud, models


async def subscribe_channel():
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

