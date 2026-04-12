#!/usr/bin/env python3
"""
RabbitMQ Worker Module — Request-Driven

Handles RabbitMQ message production and consumption triggered by HTTP requests.
Each request to /produce publishes messages, each request to /consume processes
messages from the queue with configurable delay.

This module is designed to be called by the main HTTP server.
"""

import time
import uuid
import logging
import json

logger = logging.getLogger('rabbitmq_worker')

try:
    import pika
    PIKA_AVAILABLE = True
except ImportError:
    PIKA_AVAILABLE = False
    logger.warning("pika not installed, RabbitMQ functionality disabled")


class RabbitMQWorker:
    """RabbitMQ producer/consumer triggered by HTTP requests."""

    def __init__(self, url='amqp://guest:guest@rabbitmq:5672', queue='task-queue',
                 processing_delay_ms=100):
        """Initialize RabbitMQ worker.

        Args:
            url: RabbitMQ connection URL.
            queue: Queue name for messages.
            processing_delay_ms: Delay per message processing in ms.
        """
        self.url = url
        self.queue = queue
        self.processing_delay_ms = processing_delay_ms
        self._connection = None
        self._channel = None
        self._total_produced = 0
        self._total_consumed = 0

        logger.info(
            f"RabbitMQWorker initialized: url=****, queue={queue}, "
            f"delay={processing_delay_ms}ms"
        )

    def _get_connection(self):
        """Get or create RabbitMQ connection.

        Returns:
            pika.BlockingConnection: Active connection.
        """
        if self._connection is None or self._connection.is_closed:
            logger.info(f"Connecting to RabbitMQ: {self.url}")
            params = pika.URLParameters(self.url)
            params.connection_attempts = 3
            params.retry_delay = 2
            self._connection = pika.BlockingConnection(params)
            self._channel = self._connection.channel()
            # Declare queue (idempotent)
            self._channel.queue_declare(queue=self.queue, durable=True)
            logger.info(f"Connected to RabbitMQ, queue '{self.queue}' declared")
        return self._connection

    def produce_messages(self, count=10, message_size=256):
        """Produce messages to the queue.

        Args:
            count: Number of messages to produce.
            message_size: Size of each message payload in bytes.

        Returns:
            dict: Production results.
        """
        if not PIKA_AVAILABLE:
            raise RuntimeError("pika library not available")

        start_time = time.monotonic()

        conn = self._get_connection()

        for i in range(count):
            # Create message payload
            payload = json.dumps({
                'id': str(uuid.uuid4()),
                'sequence': i,
                'size': message_size,
                'timestamp': time.time(),
                'padding': 'x' * max(0, message_size - 64)
            })

            self._channel.basic_publish(
                exchange='',
                routing_key=self.queue,
                body=payload.encode('utf-8'),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                )
            )

        elapsed_ms = (time.monotonic() - start_time) * 1000
        self._total_produced += count

        logger.info(f"Produced {count} messages to '{self.queue}' in {elapsed_ms:.2f}ms")

        return {
            'status': 'produced',
            'count': count,
            'message_size': message_size,
            'elapsed_ms': round(elapsed_ms, 2),
            'total_produced': self._total_produced
        }

    def consume_messages(self, count=10, delay_ms=None):
        """Consume messages from the queue.

        Args:
            count: Maximum number of messages to consume.
            delay_ms: Processing delay per message in ms (overrides default).

        Returns:
            dict: Consumption results.
        """
        if not PIKA_AVAILABLE:
            raise RuntimeError("pika library not available")

        delay = delay_ms if delay_ms is not None else self.processing_delay_ms
        start_time = time.monotonic()

        conn = self._get_connection()

        consumed = 0
        for _ in range(count):
            method_frame, header_frame, body = self._channel.basic_get(
                queue=self.queue, auto_ack=False
            )

            if method_frame:
                # Simulate processing delay
                if delay > 0:
                    time.sleep(delay / 1000.0)

                # Acknowledge message
                self._channel.basic_ack(method_frame.delivery_tag)
                consumed += 1
            else:
                # No more messages
                break

        elapsed_ms = (time.monotonic() - start_time) * 1000
        self._total_consumed += consumed

        logger.info(f"Consumed {consumed}/{count} messages from '{self.queue}' in {elapsed_ms:.2f}ms")

        return {
            'status': 'consumed',
            'consumed': consumed,
            'requested': count,
            'delay_ms': delay,
            'elapsed_ms': round(elapsed_ms, 2),
            'total_consumed': self._total_consumed
        }

    def get_queue_depth(self):
        """Get current queue depth (message count).

        Returns:
            int: Number of messages in queue.
        """
        if not PIKA_AVAILABLE:
            raise RuntimeError("pika library not available")

        conn = self._get_connection()
        # Queue declare with passive=True returns message count
        method_frame = self._channel.queue_declare(queue=self.queue, passive=True)
        return method_frame.method.message_count

    def close(self):
        """Close RabbitMQ connection."""
        if self._connection and not self._connection.is_closed:
            self._connection.close()
            logger.info("RabbitMQ connection closed")


# Standalone entry point for testing
if __name__ == '__main__':
    import os
    logging.basicConfig(level=logging.INFO)
    worker = RabbitMQWorker(
        url=os.environ.get('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672'),
        queue=os.environ.get('RABBITMQ_QUEUE', 'task-queue')
    )
    try:
        # Produce some messages
        result = worker.produce_messages(5, 128)
        print(f"Produced: {result}")

        # Consume them back
        result = worker.consume_messages(5)
        print(f"Consumed: {result}")
    finally:
        worker.close()
