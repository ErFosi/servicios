import aio_pika
import logging
import json
from app.sql.database import SessionLocal # pylint: disable=import-outside-toplevel
from app.sql import crud, models
import ssl

logger = logging.getLogger(__name__)



# Configura el logger
logging.basicConfig(level=logging.INFO)
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
