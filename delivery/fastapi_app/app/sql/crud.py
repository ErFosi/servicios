# -*- coding: utf-8 -*-
"""Functions that interact with the database."""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from . import models
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, or_, case


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def get_delivery(db: AsyncSession, delivery_id):
    """Load a delivery from the database."""
    return await db.get(models.Delivery, delivery_id)

async def create_delivery(db: AsyncSession, order_id: int, user_id: int):
    """Crear un nuevo registro en la tabla deliveries."""
    new_delivery = models.Delivery(order_id=order_id, user_id=user_id)
    db.add(new_delivery)
    await db.commit()
    logger.debug("Delivery creado con estado 'CREATED'")
    return new_delivery


async def update_delivery_address(db: AsyncSession, user_id: int, delivery_info: str):
    """Modificar la dirección y actualizar el estado basado en el estado actual."""
    async with db.begin():
        # Actualizar `delivery_info` y el estado basado en el estado actual
        stmt = (
            update(models.Delivery)
            .where(
                models.Delivery.user_id == user_id,
                or_(
                    models.Delivery.status == 'CREATED',
                    models.Delivery.status == 'COMPLETED'
                )
            )
            .values(
                delivery_info=delivery_info,
                status=case(
                    (models.Delivery.status == 'CREATED', 'IN_PROCESS'),
                    (models.Delivery.status == 'COMPLETED', 'DELIVERED'),
                    else_=models.Delivery.status
                )
            )
            .execution_options(synchronize_session="fetch")
        )
        result = await db.execute(stmt)
        await db.commit()

    # Comprobación para ver si se ha actualizado alguna fila
    if result.rowcount == 0:
        logger.debug("No delivery en estado 'CREATED' o 'COMPLETED' encontrado para el usuario %s. Actualización omitida.", user_id)
        return

    logger.debug("Delivery actualizado para el usuario %s con dirección: %s", user_id, delivery_info)
from sqlalchemy import update, select
import asyncio


async def change_delivery_status(db: AsyncSession, delivery_id, status):
    """Change order status in the database."""
    db_delivery = await get_delivery(db, delivery_id)
    db_delivery.status = status
    await db.commit()
    await db.refresh(db_delivery)
    logger.debug("Delivery cambiado a '%s' para el delivery %s", db_delivery.status, delivery_id)
    return db_delivery


async def change_delivery_status_done(db: AsyncSession, delivery_id):
    """Change order status in the database."""
    db_delivery = await get_delivery(db, delivery_id)

    # Cambia el estado basado en el valor de 'delivery_info'
    if db_delivery.status == models.Delivery.STATUS_CREATED:  # Si 'delivery_info' está vacío o es None
        db_delivery.status = models.Delivery.STATUS_COMPLETED
    else:
        db_delivery.status = models.Delivery.STATUS_DELIVERED

    # Actualiza la base de datos
    await db.commit()
    await db.refresh(db_delivery)
    logger.debug("Delivery cambiado a '%s' para el delivery %s", db_delivery.status, delivery_id)
    return db_delivery


async def get_delivery_by_order_id(db: AsyncSession, order_id: int):
    """Obtener un delivery por su order_id."""
    result = await db.execute(select(models.Delivery).where(models.Delivery.order_id == order_id))
    return result.scalars().first()

async def update_full_delivery(db: AsyncSession, order_id: int, delivery_data: dict):
    """Actualizar todos los campos de un delivery por order_id."""
    async with db.begin():
        stmt = (
            update(models.Delivery)
            .where(models.Delivery.order_id == order_id)
            .values(**delivery_data)
            .execution_options(synchronize_session="fetch")
        )
        result = await db.execute(stmt)
        await db.commit()

    if result.rowcount == 0:
        logger.debug("No delivery found for order_id %s. Update skipped.", order_id)
        return None

    logger.debug("Delivery with order_id %s updated successfully", order_id)
    # Devolver el objeto actualizado
    return await get_delivery_by_order_id(db, order_id)


async def delete_delivery(db: AsyncSession, order_id: int):
    """Eliminar un delivery por order_id."""
    async with db.begin():
        stmt = delete(models.Delivery).where(models.Delivery.order_id == order_id)
        result = await db.execute(stmt)
        await db.commit()

    if result.rowcount == 0:
        logger.debug("No delivery found for order_id %s. Delete skipped.", order_id)
        return False

    logger.debug("Delivery with order_id %s deleted successfully", order_id)
    return True