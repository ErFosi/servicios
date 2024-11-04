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
@router.get("/balance", response_model=schemas.BalanceResponse, summary="Get balance for current user")
async def get_user_balance(
        current_user: dict = Depends(get_current_user),  # Get the user info from token
        db: AsyncSession = Depends(get_db)
):
    """Retrieve balance for the authenticated user."""
    user_id = current_user["user_id"]
    payment = await crud.get_balance_by_user_id(db, user_id)
    return schemas.BalanceResponse(user_id=payment.user_id, balance=payment.balance)


# Route to update the balance for the current user
@router.put("/balance", response_model=schemas.BalanceResponse, summary="Update balance for current user")
async def update_user_balance(
        update_data: schemas.BalanceUpdate,
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Update balance (add or subtract) for the authenticated user."""
    if update_data.amount < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Charging the user is not allowed. Amount must be positive."
        )
    user_id = current_user["user_id"]
    new_balance, success = await crud.update_balance_by_user_id(db, user_id, update_data.amount)

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")

    return schemas.BalanceResponse(user_id=user_id, balance=new_balance)


# Admin-only route to modify the balance of another user by user_id
@router.put("/balance/{user_id}", response_model=schemas.BalanceResponse, summary="Admin: Update another user's balance")
async def admin_update_user_balance(
        user_id: int,
        update_data: schemas.BalanceUpdate,
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Admin-only: Update balance (add or subtract) for another user."""
    # Check if the current user has the "admin" role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Admins only.")

    new_balance, success = await crud.update_balance_by_user_id(db, user_id, update_data.amount)

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")

    return schemas.BalanceResponse(user_id=user_id, balance=new_balance)

@router.get("/balance/{user_id}", response_model=schemas.BalanceResponse, summary="Admin: Get another user's balance")
async def admin_get_user_balance(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin-only: Retrieve balance for another user."""
    # Check if the current user has the "admin" role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Admins only.")

    # Retrieve the balance for the specified user
    payment = await crud.get_balance_by_user_id(db, user_id)
    return schemas.BalanceResponse(user_id=payment.user_id, balance=payment.balance)