# -*- coding: utf-8 -*-
"""FastAPI router definitions."""
import logging
from typing import List

import fastapi
from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.business_logic.async_machine import Machine
from app.dependencies import get_db, get_machine
from app.sql import crud

from .auth import PUBLIC_KEY, ALGORITHM
from app.sql import schemas
from .router_utils import raise_and_log_error
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.routers.auth import create_access_token
from app.sql import crud, schemas, models
from app.dependencies import get_db
from jose import JWTError, jwt
from passlib.context import CryptContext

logger = logging.getLogger(__name__)
router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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


#Auth module
security = HTTPBearer(auto_error=False,)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
with open("/keys/pub.pem", "r") as pub_file:
    PUBLIC_KEY = pub_file.read()
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

@router.post("/register", response_model=schemas.UserData)
async def register(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        # Verifica si el usuario ya existe
        existing_user = await crud.get_user_by_username(db, user.username)
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already registered")

        # Crea el nuevo usuario
        new_user = await crud.create_user(db, user)
        return new_user

    except Exception as e:
        logger.error(f"Error during registration: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/login")
async def login(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await crud.get_user_by_username(db, user.username)

    if not db_user or not crud.verify_password(user.password, db_user.password):
        logger.error("Invalid credentials, missing user_id or username.")
        raise fastapi.HTTPException(status_code=400, detail="Invalid credentials")


    # Crear el access token (con expiración corta)
    access_token = create_access_token(
        data={"sub": db_user.username, "user_id": db_user.id, "role": db_user.rol}
    )

    # Crear el refresh token (con expiración larga)
    refresh_token = create_access_token(
        data={"sub": db_user.username, "user_id": db_user.id, "role": db_user.rol}
    )

    # Retornar ambos tokens
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/refresh")
async def refresh_token(token: str, db: AsyncSession = Depends(get_db)):
    try:
        logger.debug(f"Received token for refresh: {token}")
        # Decodificar el refresh token
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        username = payload.get("sub")

        if user_id is None or username is None:
            logger.error("Invalid refresh token, missing user_id or username.")
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        # Verificar si el usuario aún existe en la base de datos
        db_user = await crud.get_user_by_id(db, user_id)
        if not db_user:
            logger.error(f"User with ID {user_id} not found.")
            raise HTTPException(status_code=404, detail="User not found")

        # Generar un nuevo access token
        access_token = create_access_token(
            data={"sub": username, "user_id": user_id}
        )

        logger.debug("New access token generated successfully.")
        return {"access_token": access_token, "token_type": "bearer"}

    except JWTError as jwt_error:
        logger.error(f"JWT decoding error: {str(jwt_error)}")
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    except Exception as e:
        logger.error(f"Unhandled error during refresh token: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.put("/change-password", response_model=schemas.UserData)
async def change_password(
    current_password: str,
    new_password: str,
    user_id: int = None,  # Parámetro opcional
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    # Si `user_id` se proporciona, verificar que sea admin o coincida con el ID del usuario autenticado
    if user_id:
        if user.get("role") != "admin" and user.get("user_id") != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    else:
        # Si no se proporciona `user_id`, usar el ID del usuario autenticado
        user_id = user.get("user_id")

    # Obtener el usuario objetivo
    db_user = await crud.get_user_by_id(db, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Si no es admin, verificar la contraseña actual
    if user.get("role") != "admin" and not crud.verify_password(current_password, db_user.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect current password")

    # Cambiar la contraseña
    db_user.password = crud.get_password_hash(new_password)
    await db.commit()
    await db.refresh(db_user)

    return db_user


@router.delete("/delete/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    # Verificar que el usuario autenticado sea administrador
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Obtener el usuario objetivo
    db_user = await crud.get_user_by_id(db, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Eliminar al usuario
    await db.delete(db_user)
    await db.commit()

    return {"message": "User deleted successfully"}

