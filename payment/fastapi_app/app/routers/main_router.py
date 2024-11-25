# -*- coding: utf-8 -*-
"""FastAPI router definitions."""
import logging
import os

from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.security import HTTPBearer, OAuth2PasswordBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from app.business_logic.async_machine import Machine
from app.dependencies import get_db, get_machine
from app.sql import crud
from app.sql import schemas
from app.routers.router_utils import raise_and_log_error

logger = logging.getLogger(__name__)
router = APIRouter()


security = HTTPBearer(auto_error=False,)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
with open("/keys/pub.pem", "r") as pub_file:
    PUBLIC_KEY = pub_file.read()
ALGORITHM = "RS256"


  # Ensure this imports get_current_user with the token verification

router = APIRouter()

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
        return verify_access_token(token)

    except HTTPException as e:
        # Manejar específicamente las excepciones HTTP y relanzarlas
        logger.error(f"HTTPException in get_current_user: {e.detail}")
        raise e

    except JWTError as e:
        # Manejar específicamente errores relacionados al token
        logger.error(f"JWTError in get_current_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token inválido o expirado."
        )

    except Exception as e:
        # Loguear errores inesperados y evitar que escalen a un error 500
        logger.error(f"Unexpected error in get_current_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Error in token verification."
        )

# Route to get the balance for the current user
@router.get("/balance", response_model=schemas.BalanceResponse, summary="Get balance")
async def get_balance(
        user_id: int = None,  # Parámetro opcional
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Retrieve balance for the authenticated user or a specific user if admin."""
    # Si se proporciona `user_id`, verificar permisos
    if user_id:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Admins only.")
    else:
        # Si no se proporciona, usar el ID del usuario autenticado
        user_id = current_user["user_id"]

    # Obtener el balance del usuario
    payment = await crud.get_balance_by_user_id(db, user_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User balance not found")

    return schemas.BalanceResponse(user_id=payment.user_id, balance=payment.balance)


# Ruta para actualizar el balance
@router.put("/balance", response_model=schemas.BalanceResponse, summary="Update balance")
async def update_balance(
        update_data: schemas.BalanceUpdate,
        user_id: int = None,  # Parámetro opcional
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Update balance for the authenticated user or a specific user if admin."""
    # Si se proporciona `user_id`, verificar permisos
    if user_id:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Admins only.")
    else:
        # Si no se proporciona, usar el ID del usuario autenticado
        user_id = current_user["user_id"]

    # Verificar que el monto sea positivo
    if update_data.amount < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Charging the user is not allowed. Amount must be positive."
        )

    # Actualizar el balance
    new_balance, success = await crud.update_balance_by_user_id(db, user_id, update_data.amount)

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")

    return schemas.BalanceResponse(user_id=user_id, balance=new_balance)