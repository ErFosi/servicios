import asyncio
import aio_pika
import json
from app.sql.database import SessionLocal  # pylint: disable=import-outside-toplevel
from app.sql import crud, models
from app.routers import rabbitmq_publish_logs


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
    global exchange_events_name
    exchange_events_name = 'exchange'
    global exchange_events
    exchange_events = await channel.declare_exchange(name=exchange_events_name, type='topic', durable=True)

async def on_produced_message(message):
    async with message.process():
        order = json.loads(message.body)
        db = SessionLocal()
        db_delivery = await crud.get_delivery_by_order_id(db, order['id_order'])
        # db_delivery = await crud.change_delivery_status(db, db_delivery.id_delivery, models.Delivery.STATUS_DELIVERING)
        await db.close()
        asyncio.create_task(send_product(db_delivery))

async def on_create_message(message):
    async with message.process():
        order = json.loads(message.body)
        db = SessionLocal()
        delivery = await crud.create_delivery(db, order["id_order"], order["user_id"])
        data = {
            "id_order": delivery.order_id
        }
        message = json.dumps(data)
        routing_key = "events.delivery.created"
        await publish_event(message, routing_key)
        message, routing_key = await rabbitmq_publish_logs.formato_log_message("info", "delivery creado correctamente para el order " + str(delivery.order_id))
        await rabbitmq_publish_logs.publish_log(message, routing_key)
        await db.close()

async def subscribe_produced():
    # Create queue
    queue_name = "events.order.produced"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "events.order.produced"
    await queue.bind(exchange=exchange_events_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_produced_message(message)

async def subscribe_create():
    # Create queue
    queue_name = "events.order.created"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "events.order.created"
    await queue.bind(exchange=exchange_events_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_create_message(message)


async def send_product(delivery):
    data = {
        "id_order": delivery.order_id
    }
    message_body = json.dumps(data)

    # Publica el evento inicial con el estado "in process"
    routing_key = "events.order.inprocess"
    await publish_event(message_body, routing_key)

    # Espera de 10 segundos
    await asyncio.sleep(1)

    # Actualiza el estado del delivery en la base de datos
    db = SessionLocal()
    db_delivery = await crud.get_delivery(db, delivery.id)
    db_delivery = await crud.change_delivery_status_done(db, db_delivery.id)
    await db.close()

    # Cambia el routing_key en función del estado del delivery
    if db_delivery.status == models.Delivery.STATUS_DELIVERED:
        routing_key = "events.order.delivered"
    elif db_delivery.status == models.Delivery.STATUS_COMPLETED:
        routing_key = "events.order.completed"
    else:
        # En caso de otros estados, se puede definir un routing_key predeterminado o manejar el error
        # logger.warning("Estado inesperado para delivery %s: %s", delivery.id_order, db_delivery.status)
        return

    # Publica el evento final basado en el estado actualizado
    await publish_event(message_body, routing_key)
    message, routing_key = rabbitmq_publish_logs.formato_log_message("info", "delivery actualizado a " + db_delivery.status + "correctamente para el order " + db_delivery.order_id)
    await rabbitmq_publish_logs.publish_log(message, routing_key)


async def publish_event(message_body, routing_key):
    # Publish the message to the exchange
    await exchange_events.publish(
        aio_pika.Message(
            body=message_body.encode(),
            content_type="text/plain"
        ),
        routing_key=routing_key)
