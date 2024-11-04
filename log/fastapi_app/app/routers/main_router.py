import logging
import aio_pika
import asyncio
from fastapi import APIRouter, HTTPException
from typing import List

logger = logging.getLogger(__name__)

router = APIRouter()

logging.basicConfig(filename="logs.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Definir una ruta simple usando el APIRouter
@router.get("/")
async def root():
    return {"message": "Servicio de Logging escuchando logs"}
