# -*- coding: utf-8 -*-
"""Main file to start FastAPI application."""
import logging.config
import os
import asyncio
import aio_pika
from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.routers import main_router, rabbitmq
from app.sql import models
from app.sql import database
import global_variables
from global_variables.global_variables import update_system_resources_periodically, set_rabbitmq_status, get_rabbitmq_status


# Configure logging ################################################################################
print("Name: ", __name__)
logging.config.fileConfig(os.path.join(os.path.dirname(__file__), 'logging.ini'))
logger = logging.getLogger(__name__)



# OpenAPI Documentation ############################################################################
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
logger.info("Running app version %s", APP_VERSION)
DESCRIPTION = """
Monolithic manufacturing order application.
"""

# RabbitMQ connection details
RABBITMQ_URL = 'amqp://guest:guest@rabbitmq:5671/'
LOG_ROUTING_KEY = "logs.#"
EXCHANGE_NAME = "exchange"
QUEUE_NAME = "logging_queue"

tag_metadata = [

    {
        "name": "Machine",
        "description": "Endpoints related to machines",
    },
    {
        "name": "Order",
        "description": "Endpoints to **CREATE**, **READ**, **UPDATE** or **DELETE** orders.",
    },
    {
        "name": "Piece",
        "description": "Endpoints **READ** piece information.",
    },

]

app = FastAPI(
    redoc_url=None,  # disable redoc documentation.
    title="FastAPI - Monolithic app",
    description=DESCRIPTION,
    version=APP_VERSION,
    servers=[
        {"url": "/", "description": "Development"}
    ],
    license_info={
        "name": "MIT License",
        "url": "https://choosealicense.com/licenses/mit/"
    },
    openapi_tags=tag_metadata

)

app.include_router(main_router.router)

@app.on_event("startup")
async def startup_event():
    """Configuration to be executed when FastAPI server starts."""
    try:
        logger.info("Creating database tables")

        # Suscripción a canales y tareas de RabbitMQ
        await rabbitmq.subscribe_channel(aio_pika.ExchangeType.TOPIC, EXCHANGE_NAME)

        asyncio.create_task(rabbitmq.subscribe_logs(QUEUE_NAME))
        asyncio.create_task(rabbitmq.subscribe_commands_logs())
        asyncio.create_task(rabbitmq.subscribe_responses_logs())

        # Monitorización de recursos del sistema
        try:
            task = asyncio.create_task(update_system_resources_periodically(15))
        except Exception as e:
            logger.error(f"Error al monitorear recursos del sistema: {e}")

        logger.info("Despues de create_task")
    except Exception as main_exception:
        logger.error(f"Error during startup configuration: {main_exception}")

# Main #############################################################################################
# If application is run as script, execute uvicorn on port 8000
if __name__ == "__main__":
    import uvicorn

    logger.debug("App run as script")
    print("Starting uvicorn...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8003,
        log_config='logging.ini'
    )
    logger.debug("App finished as script")