import asyncio
import aio_pika
import json
from app.sql.database import SessionLocal  # pylint: disable=import-outside-toplevel
from app.sql import crud, models
from app.routers import rabbitmq_publish_logs
import ssl
import logging

logger = logging.getLogger(__name__)

# Configuración SSL
ssl_context = ssl.create_default_context(cafile="/keys/ca_cert.pem")
ssl_context.check_hostname = False  # Deshabilita la verificación del hostname
ssl_context.verify_mode = ssl.CERT_NONE  # No verifica el certificado del servidor

# Variables globales
channel = None
exchange_commands = None
exchange = None
exchange_commands_name = 'commands'
exchange_name = 'exchange'

async def subscribe_channel():
    """
    Conéctate a RabbitMQ utilizando SSL, declara los intercambios necesarios y configura el canal.
    """
    global channel, exchange_commands, exchange, exchange_commands_name, exchange_name

    try:
        logger.info("Intentando suscribirse...")

        # Establece la conexión robusta con RabbitMQ
        connection = await aio_pika.connect_robust(
            host='rabbitmq',
            port=5671,  # Puerto seguro SSL
            virtualhost='/',
            login='guest',
            password='guest',
            ssl=True,
            ssl_context=ssl_context
        )
        logger.info("Conexión establecida con éxito")

        # Crear un canal
        channel = await connection.channel()
        logger.debug("Canal creado con éxito")

        # Declarar el intercambio para "commands"
        exchange_commands = await channel.declare_exchange(
            name=exchange_commands_name,
            type='topic',
            durable=True
        )
        logger.info(f"Intercambio '{exchange_commands_name}' declarado con éxito")

        # Declarar el intercambio específico
        exchange = await channel.declare_exchange(
            name=exchange_name,
            type='topic',
            durable=True
        )
        logger.info(f"Intercambio '{exchange_name}' declarado con éxito")

    except Exception as e:
        logger.error(f"Error durante la suscripción: {e}")
        raise  # Propaga el error para manejo en niveles superiores


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
        address_check = await crud.check_address(db, order["user_id"])
        data = {
            "id_order": order.order_id,
            "status": address_check
        }
        if address_check:
            status_delivery_address_check = models.Delivery.STATUS_CREATED
        else:
            status_delivery_address_check = models.Delivery.STATUS_CANCELED

        delivery = await crud.create_delivery(db, order["id_order"], order["user_id"],status_delivery_address_check)
        message = json.dumps(data)
        routing_key = "events.delivery.checked"
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
