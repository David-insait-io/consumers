"""Main Kafka consumer with async event processing."""

import asyncio
import json
import logging
import signal
import sys
from typing import Set, Optional
from confluent_kafka import Consumer, KafkaError, KafkaException, Message

from config import Config
from llm_client import LLMClient
from worker import ConversationWorker
from progress import ProgressTracker
from logging_config import setup_logging

# Setup structured logging
logger = setup_logging()


class SimulationConsumer:
    """Kafka consumer for simulation events."""

    def __init__(self, config: Config):
        """Initialize consumer."""
        self.config = config
        self.running = False
        self.consumer: Optional[Consumer] = None
        self.llm_client: Optional[LLMClient] = None
        self.worker: Optional[ConversationWorker] = None
        self.progress_tracker = ProgressTracker()

        # Track active tasks
        self.active_tasks: Set[asyncio.Task] = set()

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False

    def _create_consumer(self) -> Consumer:
        """Create Kafka consumer."""
        conf = {
            'bootstrap.servers': self.config.kafka.bootstrap_servers,
            'group.id': self.config.kafka.consumer_group,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': self.config.kafka.auto_commit,
            'max.poll.interval.ms': self.config.kafka.max_poll_interval_ms,
            'session.timeout.ms': self.config.kafka.session_timeout_ms,
        }

        consumer = Consumer(conf)
        consumer.subscribe([self.config.kafka.topic])
        logger.info(f"Subscribed to topic: {self.config.kafka.topic}")

        return consumer

    async def _commit_offset(self, message: Message):
        """
        Commit Kafka offset for a message.

        Args:
            message: Kafka message to commit
        """
        try:
            # Run commit in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.consumer.commit,
                message
            )
            logger.debug(f"Committed offset for partition {message.partition()}")

        except KafkaException as e:
            logger.error(f"Failed to commit offset: {e}")
            raise

    async def _process_message(self, message: Message):
        """
        Process a single Kafka message.

        Args:
            message: Kafka message
        """
        try:
            # Parse message
            event_data = json.loads(message.value().decode('utf-8'))

            # Process event
            await self.worker.process_event(event_data, message)

            # Record progress
            self.progress_tracker.record_completion()

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
            self.progress_tracker.record_failure()
            # Commit anyway to skip bad message
            await self._commit_offset(message)

        except Exception as e:
            logger.error(f"Failed to process message: {e}", exc_info=True)
            self.progress_tracker.record_failure()
            # Don't commit - message will be reprocessed
            raise

    def _handle_kafka_error(self, msg: Message):
        """Handle Kafka message errors."""
        error = msg.error()

        if error.code() == KafkaError._PARTITION_EOF:
            # End of partition - not an error
            logger.debug(f"Reached end of partition {msg.partition()}")
            return

        logger.error(f"Kafka error: {error}")

    async def _consume_loop(self):
        """Main consume loop."""
        logger.info("Starting consume loop...")

        while self.running:
            # Poll for messages (blocking with timeout)
            # Run in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            msg = await loop.run_in_executor(
                None,
                self.consumer.poll,
                1.0  # 1 second timeout
            )

            if msg is None:
                # No message within timeout
                continue

            if msg.error():
                self._handle_kafka_error(msg)
                continue

            # Create task for processing message
            task = asyncio.create_task(self._process_message(msg))

            # Track task
            self.active_tasks.add(task)
            task.add_done_callback(self.active_tasks.discard)

            # Check if we should throttle
            if len(self.active_tasks) >= self.config.consumer.concurrent_conversations:
                # Wait for at least one task to complete
                if self.active_tasks:
                    await asyncio.wait(
                        self.active_tasks,
                        return_when=asyncio.FIRST_COMPLETED
                    )

    async def _shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down...")

        # Wait for active tasks to complete
        if self.active_tasks:
            logger.info(f"Waiting for {len(self.active_tasks)} active tasks to complete...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.active_tasks, return_exceptions=True),
                    timeout=self.config.consumer.shutdown_grace_period_seconds
                )
            except asyncio.TimeoutError:
                logger.warning("Shutdown grace period exceeded, cancelling remaining tasks")
                for task in self.active_tasks:
                    task.cancel()

        # Close resources
        if self.worker:
            await self.worker.close()

        if self.llm_client:
            await self.llm_client.close()

        if self.consumer:
            self.consumer.close()

        # Log final summary
        self.progress_tracker.log_final_summary()

        logger.info("Shutdown complete")

    async def run(self):
        """Run the consumer."""
        try:
            # Initialize components
            logger.info("Initializing consumer components...")

            self.consumer = self._create_consumer()
            self.llm_client = LLMClient(self.config.llm_client)
            self.worker = ConversationWorker(
                llm_client=self.llm_client,
                config=self.config.consumer,
                commit_callback=self._commit_offset
            )

            await self.worker.initialize()

            # Health check
            logger.info("Performing LLM backend health check...")
            if not await self.llm_client.health_check():
                logger.error("LLM backend health check failed")
                sys.exit(1)

            logger.info("Health check passed, starting consumer...")

            # Run consume loop
            self.running = True
            await self._consume_loop()

        except Exception as e:
            logger.error(f"Fatal error in consumer: {e}", exc_info=True)
            raise

        finally:
            await self._shutdown()


async def main():
    """Main entry point."""
    # Load configuration
    config = Config.from_env()

    logger.info("Starting Simulation Consumer")
    logger.info(f"Kafka: {config.kafka.bootstrap_servers}")
    logger.info(f"Topic: {config.kafka.topic}")
    logger.info(f"Consumer Group: {config.kafka.consumer_group}")
    logger.info(f"Concurrent Conversations: {config.consumer.concurrent_conversations}")
    logger.info(f"LLM Rate Limit: {config.consumer.llm_rate_limit_rps} RPS")

    # Create and run consumer
    consumer = SimulationConsumer(config)
    await consumer.run()


if __name__ == "__main__":
    asyncio.run(main())
