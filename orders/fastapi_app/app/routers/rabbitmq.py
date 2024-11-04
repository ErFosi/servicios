import aio_pika
import json
from app.sql.database import SessionLocal  # pylint: disable=import-outside-toplevel
from app.sql import crud
from app.sql import models, schemas
import logging
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
    logger.info("Se ha suscrito")
    channel = await connection.channel()
    logger.debug("Conexion creada")
    # Declare the exchange
    global exchange_name
    exchange_name = 'exchange'
    global exchange
    exchange = await channel.declare_exchange(name=exchange_name, type='topic', durable=True)


async def on_piece_message(message):
    async with message.process():
        piece_recieve = json.loads(message.body)
        db = SessionLocal()
        db_order = await crud.get_order(db, piece_recieve['id_order'])
        db_piece = await crud.update_piece_status(db, piece_recieve['id_piece'], models.Piece.STATUS_CREATED)
        db_pieces = await crud.get_piece_list_by_order(db, db_order.id)
        order_finished = True
        logger.info("esta llegando la pieza terminada " + str(piece_recieve['id_piece']) + " a order " + str(db_order.id))
        for piece in db_pieces:
            if piece.status == models.Piece.STATUS_QUEUED:
                order_finished = False
                break
        if order_finished:
            db_order = await crud.update_order_status(db, piece_recieve['id_order'], models.Order.STATUS_FINISHED)
            data = {
                "id_order": piece_recieve['id_order']
            }
            message_body = json.dumps(data)
            routing_key = "events.order.produced"
            await publish(message_body, routing_key)
            await rabbitmq_publish_logs.publish_log("Todas las piezas del order producidas", "logs.info.order")
        await db.close()

async def on_order_delivered_message(message):
    async with message.process():
        order = json.loads(message.body)
        db = SessionLocal()
        db_order = await crud.update_order_status(db, order['id'], models.Order.STATUS_DELIVERED)
        await rabbitmq_publish_logs.publish_log("order " + order['id'] + "delivered", "logs.info.order")
        await db.close()

async def subscribe_pieces():
    # Create a queue
    queue_name = "events.piece.produced"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "events.piece.produced"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_piece_message(message)

async def subscribe_order_finished():
    # Create a queue
    queue_name = "events.order.delivered"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "events.order.delivered"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_order_delivered_message(message)


async def on_payment_checked_message(message):
    async with message.process():
        payment = json.loads(message.body)
        db = SessionLocal()
        if payment['status']:
            db_order = await crud.update_order_status(db, payment['id_order'], models.Order.STATUS_PAYMENT_DONE)
            data = {
                "id_order": db_order.id,
                "user_id": db_order.id_client
            }
            message_body = json.dumps(data)
            routing_key = "events.order.created"
            await publish(message_body, routing_key)
            await rabbitmq_publish_logs.publish_log("El order ha sido pagado por el cliente " + str(db_order.id_client), "logs.info.order")

            # Crear las piezas de la orden
            for _ in range(db_order.number_of_pieces):
                db_piece = await crud.add_piece_to_order(db, db_order)
                data = {
                    "piece_id": db_piece.id,
                    "order_id": db_order.id
                }
                logger.info("pieza "+str(db_piece.id)+" creada para order "+str(db_order.id))
                message_body = json.dumps(data)
                routing_key = "events.piece.created"
                await publish(message_body, routing_key)
                await rabbitmq_publish_logs.publish_log("Petición de hacer pieza enviada", "logs.info.order")

            # pydantic_order = schemas.Order.from_orm(db_order)
            # order_json = pydantic_order.dict()
        else:
            await rabbitmq_publish_logs.publish_log("El balance no es suficiente para el cliente " + str(payment["id_client"]), "logs.error.order")
        await db.close()


async def subscribe_payment_checked():
    # Create a queue
    queue_name = "order.checked"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "events.order.checked"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_payment_checked_message(message)


async def publish(message_body, routing_key):
    # Publish the message to the exchange
    await exchange.publish(
        aio_pika.Message(
            body=message_body.encode(),
            content_type="text/plain"
        ),
        routing_key=routing_key)
