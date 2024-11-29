# -*- coding: utf-8 -*-
"""Main file to start FastAPI application."""
import logging.config
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.routers import main_router
from app.sql import models
from app.sql import database
import asyncio
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

    try:
        task = asyncio.create_task(update_system_resources_periodically(15))
    except Exception as e:
        logger.error(f"Error al monitorear recursos del sistema: {e}")

    logger.info("Se ha enviado")

# Main #############################################################################################
# If application is run as script, execute uvicorn on port 8000
if __name__ == "__main__":
    import uvicorn

    logger.debug("App run as script")
    print("Starting uvicorn...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8006,
        log_config='logging.ini'
    )
    logger.debug("App finished as script")
