# -*- coding: utf-8 -*-
"""Main file to start FastAPI application."""
import logging.config
import os
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.routers import main_router
from app.routers import rabbitmq
from app.routers import rabbitmq_publish_logs
import asyncio
from app.sql import models
from app.sql import database

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
    await rabbitmq.subscribe_channel()
    await rabbitmq_publish_logs.subscribe_channel()
    asyncio.create_task(rabbitmq.subscribe())

    data = {
        "message": "INFO - Servicio Machine inicializado correctamente"
    }
    message_body = json.dumps(data)
    routing_key = "logs.info.machine"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)

# Main #############################################################################################
# If application is run as script, execute uvicorn on port 8000
if __name__ == "__main__":
    import uvicorn

    logger.debug("App run as script")
    print("Starting uvicorn...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_config='logging.ini'
    )
    logger.debug("App finished as script")