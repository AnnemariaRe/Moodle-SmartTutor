import json
import logging
import os
from typing import Optional

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractRobustConnection

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
EXCHANGE_NAME = "tracking.events"

_connection: Optional[AbstractRobustConnection] = None


async def connect() -> None:
    global _connection
    _connection = await aio_pika.connect_robust(RABBITMQ_URL)
    logger.info("Connected to RabbitMQ")


async def disconnect() -> None:
    global _connection
    if _connection and not _connection.is_closed:
        await _connection.close()
        logger.info("Disconnected from RabbitMQ")


async def publish_event(event_data: dict) -> None:
    if _connection is None or _connection.is_closed:
        logger.warning("RabbitMQ not connected, skipping publish for event_id=%s", event_data.get("event_id"))
        return

    try:
        async with _connection.channel() as channel:
            exchange = await channel.declare_exchange(
                EXCHANGE_NAME,
                ExchangeType.TOPIC,
                durable=True,
            )
            routing_key = event_data.get("event_type", "unknown")
            await exchange.publish(
                aio_pika.Message(
                    body=json.dumps(event_data).encode(),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=routing_key,
            )
    except Exception:
        logger.exception("Failed to publish event_id=%s to RabbitMQ", event_data.get("event_id"))
