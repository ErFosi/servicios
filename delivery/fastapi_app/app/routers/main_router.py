# -*- coding: utf-8 -*-
"""FastAPI router definitions."""
import logging
import aio_pika
from typing import List, Optional
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_db, get_machine
from app.sql import crud
from app.sql import schemas
from .router_utils import raise_and_log_error
from app.routers import rabbitmq_publish_logs
from fastapi.security import HTTPBearer, OAuth2PasswordBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from global_variables.global_variables import rabbitmq_working, system_values
from global_variables.global_variables import get_rabbitmq_status
from fastapi.responses import JSONResponse
logger = logging.getLogger(__name__)
router = APIRouter()

# RabbitMQ Config
RABBITMQ_URL = 'amqp://guest:guest@rabbitmq:5671/'
EXCHANGE_NAME = "exchange"

with open("/keys/pub.pem", "r") as pub_file:
    PUBLIC_KEY = pub_file.read()
#delivery info###########################################################################################
delivery_info = [
    {
        "delivery_address": "Calle Falsa 123",
        "status": "In progress"
    }
]
security = HTTPBearer(auto_error=False,)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
ALGORITHM = "RS256"
def verify_access_token(token: str):
    """Verifica la validez del token JWT"""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token no encontrado o inválido."
        )
    try:
        # Decodifica el token usando la clave pública y el algoritmo especificado
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM])
        logger.debug("Token verificado exitosamente.")
        return payload  # Devuelve el payload, que contiene la información del usuario
    except JWTError as e:
        # Loggear el error específico antes de lanzar la excepción
        logger.error(f"JWTError en la verificación del token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token inválido o expirado."
        )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        # Verificar si no hay credenciales en la cabecera
        if credentials is None or not credentials.credentials:
            logger.warning("No token provided in Authorization header.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No token provided."
            )

        # Verificar el token extraído
        token = credentials.credentials
        logger.debug("Token extracted, proceeding to verify.")

        # Obtener el payload del token
        payload = verify_access_token(token)

        # Obtener user_id y role del payload
        user_id = payload.get("user_id")
        role = payload.get("role")

        if user_id is None or role is None:
            logger.error("Token inválido: falta user_id o role.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token inválido."
            )

        # Retornar el user_id y role para que sean usados en los endpoints
        return {"user_id": user_id, "role": role}

    except HTTPException as e:
        logger.error(f"HTTPException in get_current_user: {e.detail}")
        raise e

    except JWTError as e:
        logger.error(f"JWTError in get_current_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token inválido o expirado."
        )

    except Exception as e:
        logger.error(f"Unexpected error in get_current_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Error in token verification."
        )

@router.get(
    "/pruebalog",
    summary="Prueba de enviar log",
    response_model=schemas.Message,
)
async def health_check():
    """Endpoint to check if everything started correctly."""
    message, routing_key = await rabbitmq_publish_logs.formato_log_message("debug", "prueba kaixo")
    await rabbitmq_publish_logs.publish_log(message, routing_key)
    return {
        "detail": "OK"
    }

#Delivery info###########################################################################################
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
@router.post(
    "/create_address",
    response_model=schemas.UserAddress,
    summary="Create a new address",
    status_code=status.HTTP_201_CREATED,
    tags=["Address"]
)
async def create_address(
    address_data: schemas.UserAddressCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new address.
    - If user_id is not provided, use current_user["user_id"].
    """
    user_id = address_data.user_id or current_user["user_id"]
    role = current_user["role"]

    # Si el usuario no es admin, verificar que no intente crear para otro user_id
    if role != "admin" and user_id != current_user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return await crud.create_address(db, user_id, address_data.address, address_data.zip_code)


@router.post(
    "/create_delivery",
    response_model=schemas.Delivery,
    summary="Create a new delivery",
    status_code=status.HTTP_201_CREATED,
    tags=["Delivery"]
)
@router.post(
    "/create_delivery",
    response_model=schemas.Delivery,
    summary="Create a new delivery",
    status_code=status.HTTP_201_CREATED,
    tags=["Delivery"]
)
async def create_delivery(
    delivery_data: schemas.DeliveryCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new delivery.
    - If user_id is not provided, use current_user["user_id"].
    """
    try:
        user_id = delivery_data.user_id or current_user["user_id"]
        role = current_user["role"]

        # Si el usuario no es admin, verificar que no intente crear para otro user_id
        if role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        logger.debug(f"Attempting to create delivery: user_id={user_id}, order_id={delivery_data.order_id}")
        result = await crud.create_delivery(db, user_id, delivery_data.order_id)
        logger.debug(f"Delivery successfully created: {result}")
        return result

    except HTTPException as http_error:
        logger.error(f"HTTP error during delivery creation: {http_error.detail}")
        raise http_error

    except Exception as e:
        logger.error(f"Unexpected error during delivery creation: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get(
    "/get_address",
    response_model=schemas.UserAddress,
    summary="Get address by user ID",
    status_code=status.HTTP_200_OK,
    tags=["Address"]
)
async def get_address(
    user_id: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get address.
    - If user_id is not provided, use current_user["user_id"].
    """
    user_id = user_id or current_user["user_id"]
    role = current_user["role"]

    # Si el usuario no es admin, verificar que no intente acceder a otro user_id
    if role != "admin" and user_id != current_user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    address = await crud.get_address_by_user_id(db, user_id)
    if not address:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")

    return address


@router.get(
    "/get_delivery",
    response_model=schemas.Delivery,
    summary="Get delivery by order ID",
    status_code=status.HTTP_200_OK,
    tags=["Delivery"]
)
async def get_delivery(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get delivery.
    - Admins can access any delivery.
    - Regular users can only access their own deliveries.
    """
    role = current_user["role"]
    delivery = await crud.get_delivery_by_order_id(db, order_id)

    if not delivery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    # Si el usuario no es admin, verificar que sea el propietario
    if role != "admin" and delivery.user_id != current_user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return delivery


@router.put(
    "/update_address",
    response_model=schemas.UserAddress,
    summary="Update address",
    status_code=status.HTTP_200_OK,
    tags=["Address"]
)
async def update_address(
    address_data: schemas.UserAddressCreate,
    user_id: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update address.
    - If user_id is not provided, use current_user["user_id"].
    """
    user_id = user_id or current_user["user_id"]
    role = current_user["role"]

    # Si el usuario no es admin, verificar que no intente actualizar otro user_id
    if role != "admin" and user_id != current_user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    updated_address = await crud.update_address(db, user_id, address_data.address, address_data.zip_code)
    if not updated_address:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")

    return updated_address


@router.put(
    "/update_delivery",
    response_model=schemas.Delivery,
    summary="Update delivery, only admins can update a delivery",
    status_code=status.HTTP_200_OK,
    tags=["Delivery"]
)
async def update_delivery(
    order_id: int,
    delivery_data: schemas.DeliveryUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update delivery.
    - If user_id is not provided, use current_user["user_id"].
    """
    role = current_user["role"]
    delivery = await crud.get_delivery_by_order_id(db, order_id)

    if not delivery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    # Si el usuario no es admin, verificar que sea el propietario
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    updated_delivery = await crud.update_delivery(db, order_id, delivery_data.status)
    return updated_delivery


@router.delete(
    "/delete_address",
    summary="Delete address",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Address"]
)
async def delete_address(
    user_id: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete address.
    - If user_id is not provided, use current_user["user_id"].
    """
    user_id = user_id or current_user["user_id"]
    role = current_user["role"]

    # Si el usuario no es admin, verificar que no intente eliminar otro user_id
    if role != "admin" and user_id != current_user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deleted = await crud.delete_address(db, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")


@router.delete(
    "/delete_delivery",
    summary="Delete delivery",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Delivery"]
)
async def delete_delivery(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete delivery.
    - Admins can delete any delivery.
    - Regular users can only delete their own deliveries.
    """
    role = current_user["role"]
    delivery = await crud.get_delivery_by_order_id(db, order_id)

    if not delivery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    # Si el usuario no es admin, verificar que sea el propietario
    if role != "admin" :
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deleted = await crud.delete_delivery(db, order_id)
    return {"detail": "Delivery deleted successfully"}

