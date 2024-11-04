# -*- coding: utf-8 -*-
"""FastAPI router definitions."""
import logging
import aio_pika
from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_db, get_machine
from app.sql import crud
from app.sql import schemas
from .router_utils import raise_and_log_error
from app.routers import rabbitmq_publish_logs
from fastapi.security import HTTPBearer, OAuth2PasswordBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

logger = logging.getLogger(__name__)
router = APIRouter()

# RabbitMQ Config
RABBITMQ_URL = 'amqp://guest:guest@localhost:5672/'
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

@router.put(
    "/update_delivery_address",
    response_model=schemas.Message,
    summary="Update delivery address and status",
    status_code=status.HTTP_200_OK,
    tags=["Delivery"]
)
async def update_delivery(
    delivery_info: str,
    current_user: dict = Depends(get_current_user),  # Obtener la información del usuario actual
    db: AsyncSession = Depends(get_db)
):
    """Update delivery address and status."""
    # Obtener el user_id y el rol del usuario actual desde el token
    user_id = current_user["user_id"]
    logger.debug("PUT '/update_delivery_address' endpoint called for user_id: %s", user_id)

    try:
        # Actualizar la dirección de entrega y el estado
        await crud.update_delivery_address(db, user_id, delivery_info)
    except Exception as e:
        logger.error("Error updating delivery: %s", str(e))
        raise HTTPException(status_code=500, detail="Error updating delivery")

    return {"detail": "Delivery address and status updated successfully"}


@router.get(
    "/get_delivery/{order_id}",
    response_model=schemas.Delivery,
    summary="Get delivery by order ID",
    status_code=status.HTTP_200_OK,
    tags=["Delivery"]
)
async def get_delivery(
    order_id: int,
    current_user: dict = Depends(get_current_user),  # Obtener información del usuario actual
    db: AsyncSession = Depends(get_db)
):
    """Get delivery by order ID."""
    logger.debug("GET '/get_delivery/{order_id}' endpoint called with order_id: %s", order_id)

    # Obtener el user_id y el rol del usuario actual
    user_id = current_user["user_id"]
    role = current_user["role"]

    # Permitir acceso si el usuario es admin o es el propietario del pedido
    delivery = await crud.get_delivery_by_order_id(db, order_id)
    if not delivery:
        message = f"Delivery not found for order_id: {order_id}"
        level = "error"
        message, routing_key = rabbitmq_publish_logs.formato_log_message(level, message)
        await rabbitmq_publish_logs.publish_log(message, routing_key)
        raise_and_log_error(logger, status.HTTP_409_CONFLICT, f"The token is expired, please log in again")

        logger.error("Delivery not found for order_id: %s", order_id)
        raise HTTPException(status_code=404, detail="Delivery not found")

    # Verificar que el usuario es el propietario o tiene rol de admin
    if delivery.user_id != user_id and role != "admin":
        logger.warning("Access denied for user_id: %s with role: %s", user_id, role)
        raise HTTPException(status_code=403, detail="Access denied")

    return delivery


@router.put(
    "/admin/update_delivery/{order_id}",
    response_model=schemas.Delivery,
    summary="Admin: Update entire delivery",
    status_code=status.HTTP_200_OK,
    tags=["Delivery"]
)
async def update_full_delivery(
    order_id: int,
    delivery_data: schemas.DeliveryUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update entire delivery details. Only accessible by admins."""
    # Verificar rol de administrador
    if current_user["role"] != "admin":
        logger.warning("Access denied for user_id: %s with role: %s", current_user["user_id"], current_user["role"])
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Convertir los datos a un diccionario excluyendo valores no definidos
    delivery_data_dict = delivery_data.dict(exclude_unset=True)


    updated_delivery = await crud.update_full_delivery(db, order_id, delivery_data_dict)
    if not updated_delivery:
        logger.error("Delivery not found for order_id: %s", order_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    return updated_delivery


@router.delete(
    "/admin/delete_delivery/{order_id}",
    summary="Admin: Delete a delivery",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Delivery"]
)
async def delete_delivery(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a delivery by order ID. Only accessible by admins."""
    # Verificar rol de administrador
    if current_user["role"] != "admin":
        logger.warning("Access denied for user_id: %s with role: %s", current_user["user_id"], current_user["role"])
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


    deleted = await crud.delete_delivery(db, order_id)
    if not deleted:
        logger.error("Delivery not found for order_id: %s", order_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    return {"detail": "Delivery deleted successfully"}
