import logging
import aio_pika
import asyncio
from fastapi import APIRouter, HTTPException,status
from typing import List
from global_variables.global_variables import rabbitmq_working, system_values
from global_variables.global_variables import get_rabbitmq_status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()

logging.basicConfig(filename="logs.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Definir una ruta simple usando el APIRouter
@router.get("/")
async def root():
    return {"message": "Servicio de Logging escuchando logs"}


@router.get("/health", tags=["Health check"])
async def health_check():
    """
    Endpoint de health check para verificar el estado de RabbitMQ y los recursos del sistema.
    """
    try:
        # Verificar si RabbitMQ está funcionando
        if not get_rabbitmq_status():
            logger.error("RabbitMQ no está funcionando correctamente.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RabbitMQ no está disponible"
            )

        cpu = system_values["CPU"]
        memory = system_values["Memory"]

        # Registra los valores de los recursos
        logger.info("System resources: CPU = %s%%, Memory = %s%%", cpu, memory)

        # Verificar si el uso de CPU o memoria es demasiado alto
        MAX_CPU_USAGE = 90  # 90% de uso de CPU
        MAX_MEMORY_USAGE = 90  # 90% de uso de memoria

        if cpu > MAX_CPU_USAGE:
            logger.error("Uso de CPU demasiado alto: %s%%", cpu)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Uso de CPU demasiado alto: {cpu}%"
            )

        if memory > MAX_MEMORY_USAGE:
            logger.error("Uso de memoria demasiado alto: %s%%", memory)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Uso de memoria demasiado alto: {memory}%"
            )

        # Si todo está bien, devolver un mensaje de éxito
        return JSONResponse(content={
            "status": "OK",
            "cpu_usage": cpu,
            "memory_usage": memory
        }, status_code=status.HTTP_200_OK)

    except Exception as e:
        # Captura y loguea excepciones generales
        logger.error(f"Error inesperado en health_check: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno en el servidor."
        )