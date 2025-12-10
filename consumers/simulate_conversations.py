"""Kafka consumer for conversation simulation."""

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Set, Optional, Callable
from confluent_kafka import Consumer, Producer, KafkaError, KafkaException, Message

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from llm_client import LLMClient
from base_worker import BaseConversationWorker
from schemas import SimulationEvent, ConversationResult
from progress import ProgressTracker
from logging_config import setup_logging, ConversationLogger

# Setup structured logging
setup_logging()
logger = ConversationLogger()


class ConversationSimulationWorker(BaseConversationWorker):
    """Worker for simulating conversations via Kafka events."""

    def __init__(
        self,
        llm_client: LLMClient,
        config,
        commit_callback,
        publish_callback: Optional[Callable] = None,
        results_dir: Optional[Path] = None
    ):
        super().__init__(llm_client, config)
        self.commit_callback = commit_callback
        self.publish_callback = publish_callback  # Callback to publish to evaluation topic
        self.results_dir = results_dir or Path("results")

    async def process_event(self, event_data: dict, kafka_message):
        """
        Process a single simulation event.

        Args:
            event_data: Event data dictionary
            kafka_message: Kafka message object (for committing offset)
        """
        async with self.semaphore:
            simulation_id = event_data.get('id', 'unknown')

            try:
                event = SimulationEvent(**event_data)

                logger.conversation_started(
                    simulation_id=event.id,
                    persona_name=event.testPersona.name,
                    test_goal=event.testGoal
                )

                result = await self.run_conversation(event)
                await self._save_result(result)

                # Publish to evaluation topic if callback provided
                if self.publish_callback:
                    await self.publish_callback(result)

                await self.commit_callback(kafka_message)

                logger.conversation_completed(
                    simulation_id=event.id,
                    iterations=result.total_iterations,
                    duration_ms=result.duration_ms,
                    end_reason=result.end_reason,
                    goal_reached=result.goal_reached
                )

            except asyncio.TimeoutError:
                logger.conversation_failed(
                    simulation_id=simulation_id,
                    error="timeout"
                )
                raise

            except Exception as e:
                logger.conversation_failed(
                    simulation_id=simulation_id,
                    error=str(e)
                )
                raise

    async def _save_result(self, result: ConversationResult):
        """Save result to local file."""
        try:
            self.results_dir.mkdir(exist_ok=True)
            output_file = self.results_dir / f"result_{result.simulation_id}.json"

            with open(output_file, 'w') as f:
                json.dump(result.model_dump(), f, indent=2)

            logger.result_saved(
                simulation_id=result.simulation_id,
                file_path=str(output_file)
            )

        except Exception as e:
            logger.conversation_failed(
                simulation_id=result.simulation_id,
                error=f"Failed to save result: {e}"
            )
            raise


class SimulationConsumer:
    """Kafka consumer for simulation events."""

    EVALUATION_TOPIC = "evaluation-events"

    def __init__(
        self,
        config: Config,
        results_dir: Optional[Path] = None,
        evaluation_topic: Optional[str] = None
    ):
        """Initialize consumer."""
        self.config = config
        self.results_dir = results_dir
        self.evaluation_topic = evaluation_topic or self.EVALUATION_TOPIC
        self.running = False
        self.consumer: Optional[Consumer] = None
        self.producer: Optional[Producer] = None
        self.llm_client: Optional[LLMClient] = None
        self.worker: Optional[ConversationSimulationWorker] = None
        self.progress_tracker = ProgressTracker()
        self.active_tasks: Set[asyncio.Task] = set()

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logging.info(f"Received signal {signum}, initiating graceful shutdown...")
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
        logging.info(f"Subscribed to topic: {self.config.kafka.topic}")

        return consumer

    def _create_producer(self) -> Producer:
        """Create Kafka producer for evaluation topic."""
        conf = {
            'bootstrap.servers': self.config.kafka.bootstrap_servers,
        }
        return Producer(conf)

    async def _publish_to_evaluation(self, result: ConversationResult):
        """Publish conversation result to evaluation topic."""
        try:
            message = json.dumps(result.model_dump()).encode('utf-8')

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.producer.produce(
                    self.evaluation_topic,
                    value=message,
                    callback=self._delivery_callback
                )
            )
            # Flush to ensure message is sent
            self.producer.poll(0)

            logging.info(f"Published to {self.evaluation_topic}: {result.simulation_id}")

        except Exception as e:
            logging.error(f"Failed to publish to evaluation topic: {e}")
            raise

    def _delivery_callback(self, err, msg):
        """Callback for producer delivery reports."""
        if err:
            logging.error(f"Message delivery failed: {err}")
        else:
            logging.debug(f"Message delivered to {msg.topic()} [{msg.partition()}]")

    async def _commit_offset(self, message: Message):
        """Commit Kafka offset for a message."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.consumer.commit,
                message
            )
            logging.debug(f"Committed offset for partition {message.partition()}")

        except KafkaException as e:
            logging.error(f"Failed to commit offset: {e}")
            raise

    async def _process_message(self, message: Message):
        """Process a single Kafka message."""
        try:
            event_data = json.loads(message.value().decode('utf-8'))
            await self.worker.process_event(event_data, message)
            self.progress_tracker.record_completion()

        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse message: {e}")
            self.progress_tracker.record_failure()
            await self._commit_offset(message)

        except Exception as e:
            logging.error(f"Failed to process message: {e}", exc_info=True)
            self.progress_tracker.record_failure()
            raise

    def _handle_kafka_error(self, msg: Message):
        """Handle Kafka message errors."""
        error = msg.error()

        if error.code() == KafkaError._PARTITION_EOF:
            logging.debug(f"Reached end of partition {msg.partition()}")
            return

        logging.error(f"Kafka error: {error}")

    async def _consume_loop(self):
        """Main consume loop."""
        logging.info("Starting consume loop...")

        while self.running:
            loop = asyncio.get_event_loop()
            msg = await loop.run_in_executor(
                None,
                self.consumer.poll,
                1.0
            )

            if msg is None:
                continue

            if msg.error():
                self._handle_kafka_error(msg)
                continue

            task = asyncio.create_task(self._process_message(msg))
            self.active_tasks.add(task)
            task.add_done_callback(self.active_tasks.discard)

            if len(self.active_tasks) >= self.config.consumer.concurrent_conversations:
                if self.active_tasks:
                    await asyncio.wait(
                        self.active_tasks,
                        return_when=asyncio.FIRST_COMPLETED
                    )

    async def _shutdown(self):
        """Graceful shutdown."""
        logging.info("Shutting down...")

        if self.active_tasks:
            logging.info(f"Waiting for {len(self.active_tasks)} active tasks to complete...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.active_tasks, return_exceptions=True),
                    timeout=self.config.consumer.shutdown_grace_period_seconds
                )
            except asyncio.TimeoutError:
                logging.warning("Shutdown grace period exceeded, cancelling remaining tasks")
                for task in self.active_tasks:
                    task.cancel()

        if self.worker:
            await self.worker.close()

        if self.llm_client:
            await self.llm_client.close()

        if self.consumer:
            self.consumer.close()

        if self.producer:
            self.producer.flush()  # Ensure all messages are sent

        self.progress_tracker.log_final_summary()
        logging.info("Shutdown complete")

    async def run(self):
        """Run the consumer."""
        try:
            logging.info("Initializing consumer components...")

            self.consumer = self._create_consumer()
            self.producer = self._create_producer()
            self.llm_client = LLMClient(self.config.llm_client)
            self.worker = ConversationSimulationWorker(
                llm_client=self.llm_client,
                config=self.config.consumer,
                commit_callback=self._commit_offset,
                publish_callback=self._publish_to_evaluation,
                results_dir=self.results_dir
            )

            await self.worker.initialize()

            logging.info(f"Publishing results to evaluation topic: {self.evaluation_topic}")
            logging.info("Performing LLM backend health check...")
            if not await self.llm_client.health_check():
                logging.error("LLM backend health check failed")
                sys.exit(1)

            logging.info("Health check passed, starting consumer...")

            self.running = True
            await self._consume_loop()

        except Exception as e:
            logging.error(f"Fatal error in consumer: {e}", exc_info=True)
            raise

        finally:
            await self._shutdown()


async def main():
    """Main entry point."""
    config = Config.from_env()

    logging.info("Starting Simulation Consumer")
    logging.info(f"Kafka: {config.kafka.bootstrap_servers}")
    logging.info(f"Topic: {config.kafka.topic}")
    logging.info(f"Consumer Group: {config.kafka.consumer_group}")
    logging.info(f"Concurrent Conversations: {config.consumer.concurrent_conversations}")
    logging.info(f"LLM Rate Limit: {config.consumer.llm_rate_limit_rps} RPS")

    consumer = SimulationConsumer(config)
    await consumer.run()


if __name__ == "__main__":
    asyncio.run(main())
