import asyncio
import json
import logging
import os

import aio_pika

from app.mastery import handle_event

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
EXCHANGE_NAME = "tracking.events"
QUEUE_NAME = "adaptive_student_events"
RETRY_DELAY = 5


async def consume_events() -> None:
    while True:
        try:
            await _run_consumer()
        except asyncio.CancelledError:
            logger.info("Consumer task cancelled — shutting down")
            raise
        except Exception as exc:
            logger.warning(
                "Consumer error: %s — reconnecting in %ss", exc, RETRY_DELAY
            )
            await asyncio.sleep(RETRY_DELAY)


async def _run_consumer() -> None:
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        exchange = await channel.declare_exchange(
            EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await channel.declare_queue(QUEUE_NAME, durable=True)

        await queue.bind(exchange, routing_key="quiz_attempt_submitted")
        await queue.bind(exchange, routing_key="assign_submission_graded")
        await queue.bind(exchange, routing_key="lesson_completed")
        await queue.bind(exchange, routing_key="lesson_answer_submitted")

        logger.info(
            "Adaptive consumer ready — exchange=%s queue=%s",
            EXCHANGE_NAME,
            QUEUE_NAME,
        )

        async with queue.iterator() as qiter:
            async for message in qiter:
                async with message.process():
                    try:
                        event = json.loads(message.body)
                        await handle_event(event)
                    except Exception:
                        logger.exception(
                            "Failed to process message: %s", message.body[:200]
                        )
