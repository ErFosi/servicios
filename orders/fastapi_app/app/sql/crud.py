# -*- coding: utf-8 -*-
"""Functions that interact with the database."""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from . import models
from sqlalchemy import update

logger = logging.getLogger(__name__)


# order functions ##################################################################################
async def create_order_from_schema(db: AsyncSession, order):
    """Persist a new order into the database."""
    db_order = models.Order(
        number_of_pieces=order.number_of_pieces,
        description=order.description,
        status=models.Order.STATUS_PAYMENT_PENDING,
        id_client=order.id_client
    )
    db.add(db_order)
    await db.commit()
    await db.refresh(db_order)
    return db_order


async def add_piece_to_order(db: AsyncSession, order):
    """Creates piece and adds it to order."""
    piece = models.Piece()
    piece.order = order
    db.add(piece)
    await db.commit()
    await db.refresh(order)
    return piece


async def get_order_list(db: AsyncSession):
    """Load all the orders from the database."""
    return await get_list(db, models.Order)


async def get_order(db: AsyncSession, order_id):
    """Load an order from the database."""
    stmt = select(models.Order).join(models.Order.pieces).where(models.Order.id == order_id)
    order = await get_element_statement_result(db, stmt)
    return order


async def delete_order(db: AsyncSession, order_id):
    """Delete order from the database."""
    return await delete_element_by_id(db, models.Order, order_id)


async def update_order_status(db: AsyncSession, order_id, status):
    """Persist new order status on the database."""
    db_order = await get_element_by_id(db, models.Order, order_id)
    if db_order is not None:
        db_order.status = status
        await db.commit()
        await db.refresh(db_order)
    return db_order


# Piece functions ##################################################################################
async def get_piece_list_by_status(db: AsyncSession, status):
    """Get all pieces with a given status from the database."""
    # query = db.query(models.Piece).filter_by(status=status)
    # return query.all()
    stmt = select(models.Piece).where(models.Piece.status == status)
    # result = await db.execute(stmt)
    # item_list = result.scalars().all()

    return await get_list_statement_result(db, stmt)


async def update_piece_status(db: AsyncSession, piece_id, status):
    """Persist new piece status on the database."""
    db_piece = await get_element_by_id(db, models.Piece, piece_id)
    if db_piece is not None:
        db_piece.status = status
        await db.commit()
        await db.refresh(db_piece)
    return db_piece


async def update_piece_manufacturing_date_to_now(db: AsyncSession, piece_id):
    """For a given piece_id, sets piece's manufacturing_date to current datetime."""
    db_piece = await get_element_by_id(db, models.Piece, piece_id)
    if db_piece is not None:
        db_piece.manufacturing_date = datetime.now()
        await db.commit()
        await db.refresh(db_piece)
    return db_piece


async def get_piece_list(db: AsyncSession):
    """Load all the orders from the database."""
    stmt = select(models.Piece).join(models.Piece.order)
    pieces = await get_list_statement_result(db, stmt)
    return pieces

async def get_piece_list_by_order(db: AsyncSession, order_id: int):
    """Load all pieces from the database for a specific order."""
    stmt = (
        select(models.Piece)
        .join(models.Piece.order)
        .where(models.Piece.order_id == order_id)  # Filtra por order_id
    )
    pieces = await get_list_statement_result(db, stmt)
    return pieces


async def get_piece(db: AsyncSession, piece_id):
    """Load a piece from the database."""
    return await get_element_by_id(db, models.Piece, piece_id)


# Generic functions ################################################################################
# READ
async def get_list(db: AsyncSession, model):
    """Retrieve a list of elements from database"""
    result = await db.execute(select(model))
    item_list = result.unique().scalars().all()
    return item_list


async def get_list_statement_result(db: AsyncSession, stmt):
    """Execute given statement and return list of items."""
    result = await db.execute(stmt)
    item_list = result.unique().scalars().all()
    return item_list


async def get_element_statement_result(db: AsyncSession, stmt):
    """Execute statement and return a single items"""
    result = await db.execute(stmt)
    item = result.scalar()
    return item


async def get_element_by_id(db: AsyncSession, model, element_id):
    """Retrieve any DB element by id."""
    if element_id is None:
        return None

    element = await db.get(model, element_id)
    return element


# DELETE
async def delete_element_by_id(db: AsyncSession, model, element_id):
    """Delete any DB element by id."""
    element = await get_element_by_id(db, model, element_id)
    if element is not None:
        await db.delete(element)
        await db.commit()
    return element

async def update_order(db: AsyncSession, order_id: int, update_data: dict):
    """Actualizar los campos de una orden específicos según el `order_id`."""
    async with db.begin():
        stmt = (
            update(models.Order)
            .where(models.Order.id == order_id)
            .values(**update_data)
            .execution_options(synchronize_session="fetch")
        )
        result = await db.execute(stmt)
        await db.commit()

    if result.rowcount == 0:
        return None  # Orden no encontrada
    return await get_order(db, order_id)  # Retornar la orden actualizada si se realizó el update
