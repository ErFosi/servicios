# -*- coding: utf-8 -*-
"""FastAPI router definitions."""
import logging
import requests
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.business_logic.async_machine import Machine
from app.dependencies import get_db, get_machine
from app.sql import crud
from app.sql import schemas, models
from .router_utils import raise_and_log_error

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/",
    summary="Health check endpoint",
    response_model=schemas.Message,
)
async def health_check():
    """Endpoint to check if everything started correctly."""
    logger.debug("GET '/' endpoint called.")
    return {
        "detail": "OK"
    }


# Machine ##########################################################################################
@router.get(
    "/machine/status",
    summary="Retrieve machine status",
    response_model=schemas.MachineStatusResponse,
    tags=['Machine']
)
async def machine_status(
        my_machine: Machine = Depends(get_machine)
):
    """Retrieve machine status"""
    logger.debug("GET '/machine/status' endpoint called.")
    machine_status = await crud.get_status_of_machine()
    return machine_status

