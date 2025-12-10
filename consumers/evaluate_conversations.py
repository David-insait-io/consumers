"""Kafka consumer for conversation goal evaluation."""

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Set, Optional, List
from confluent_kafka import Consumer, KafkaError, KafkaException, Message

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from llm_client import LLMClient
from base_worker import BaseConversationWorker
from schemas import (
    ConversationMessage,
    ConversationResult,
    EvaluationResult,
)
from progress import ProgressTracker
from logging_config import setup_logging, ConversationLogger

# Setup structured logging
setup_logging()
logger = ConversationLogger()


class ConversationEvaluationWorker(BaseConversationWorker):
    """Worker for evaluating if conversations achieved their test goal."""

    def __init__(
        self,
        llm_client: LLMClient,
        config,
        commit_callback=None,
        results_dir: Optional[Path] = None,
    ):
        super().__init__(llm_client, config)
        self.commit_callback = commit_callback
        self.results_dir = results_dir or Path("results")

    async def evaluate_conversation(
        self,
        conversation_result: ConversationResult
    ) -> EvaluationResult:
        """
        Evaluate if a conversation achieved its test goal.

        Args:
            conversation_result: The conversation to evaluate

        Returns:
            EvaluationResult with goal achievement assessment
        """
        import time
        start_time = time.time()

        # Build conversation transcript
        transcript = self._build_transcript(conversation_result.conversation_history)

        # Evaluate goal achievement
        goal_achieved, reasoning = await self._evaluate_goal(
            simulation_id=conversation_result.simulation_id,
            transcript=transcript,
            test_goal=conversation_result.test_goal
        )

        duration_ms = int((time.time() - start_time) * 1000)

        return EvaluationResult(
            simulation_id=conversation_result.simulation_id,
            flow_version_id=conversation_result.flow_version_id,
            test_goal=conversation_result.test_goal,
            goal_achieved=goal_achieved,
            reasoning=reasoning,
            conversation_history=conversation_result.conversation_history,
            duration_ms=duration_ms
        )

    def _build_transcript(self, history: List[ConversationMessage]) -> str:
        """Build a readable transcript from conversation history."""
        lines = []
        for msg in history:
            role = "CHATBOT" if msg.role == "assistant" else "USER"
            lines.append(f"{role}: {msg.content}")
        return "\n\n".join(lines)

    async def _evaluate_goal(
        self,
        simulation_id: str,
        transcript: str,
        test_goal: str
    ) -> tuple[bool, str]:
        """
        Evaluate if the test goal was achieved.

        Returns:
            Tuple of (goal_achieved: bool, reasoning: str)
        """
        system_prompt = f"""You are evaluating if a conversation achieved its intended goal.

TEST GOAL: {test_goal}

INSTRUCTIONS:
1. Carefully read the conversation transcript
2. Determine if the goal was achieved based on the conversation
3. Provide your assessment

Respond in JSON format:
{{"goal_achieved": true/false, "reasoning": "<brief explanation>"}}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"CONVERSATION TRANSCRIPT:\n\n{transcript}"}
        ]

        async with self.rate_limiter:
            logger.llm_request(
                simulation_id=simulation_id,
                model=self.config.persona_llm_model,
                purpose="evaluate_goal"
            )

            try:
                response = await self.llm_client.chat_completion(
                    messages=messages,
                    model=self.config.persona_llm_model,
                    temperature=1
                )

                # Parse JSON response
                result = json.loads(response.strip())
                return (
                    bool(result.get("goal_achieved", False)),
                    result.get("reasoning", "No reasoning provided")
                )

            except json.JSONDecodeError:
                return False, f"Failed to parse evaluation response: {response[:100]}"

            except Exception as e:
                logger.llm_error(
                    simulation_id=simulation_id,
                    error=str(e),
                    attempt=1
                )
                return False, f"Evaluation error: {str(e)}"

    async def process_event(self, event_data: dict, kafka_message=None):
        """
        Process a conversation result for evaluation.

        Args:
            event_data: ConversationResult data dictionary
            kafka_message: Kafka message object (for committing offset)
        """
        async with self.semaphore:
            simulation_id = event_data.get('simulation_id', 'unknown')

            try:
                conversation_result = ConversationResult(**event_data)

                logging.info(f"Evaluating conversation: {simulation_id}")

                evaluation = await self.evaluate_conversation(conversation_result)
                await self._save_result(evaluation)

                if kafka_message and self.commit_callback:
                    await self.commit_callback(kafka_message)

                goal_status = "ACHIEVED" if evaluation.goal_achieved else "NOT ACHIEVED"
                logging.info(f"Evaluation complete: {simulation_id} - Goal: {goal_status}")

                return evaluation

            except Exception as e:
                logging.error(f"Evaluation failed for {simulation_id}: {e}")
                raise

    async def _save_result(self, result: EvaluationResult):
        """Save evaluation result to local file."""
        try:
            self.results_dir.mkdir(exist_ok=True)
            output_file = self.results_dir / f"eval_{result.simulation_id}.json"

            with open(output_file, 'w') as f:
                json.dump(result.model_dump(), f, indent=2)

            logging.info(f"Evaluation saved: {output_file}")

        except Exception as e:
            logging.error(f"Failed to save evaluation: {e}")
            raise


class EvaluationConsumer:
    """Kafka consumer for conversation evaluation events."""

    def __init__(
        self,
        config: Config,
        results_dir: Optional[Path] = None,
    ):
        """Initialize consumer."""
        self.config = config
        self.results_dir = results_dir
        self.running = False
        self.consumer: Optional[Consumer] = None
        self.llm_client: Optional[LLMClient] = None
        self.worker: Optional[ConversationEvaluationWorker] = None
        self.progress_tracker = ProgressTracker()
        self.active_tasks: Set[asyncio.Task] = set()

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logging.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False

    def _create_consumer(self, topic: str) -> Consumer:
        """Create Kafka consumer."""
        conf = {
            'bootstrap.servers': self.config.kafka.bootstrap_servers,
            'group.id': f"{self.config.kafka.consumer_group}-evaluator",
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': self.config.kafka.auto_commit,
            'max.poll.interval.ms': self.config.kafka.max_poll_interval_ms,
            'session.timeout.ms': self.config.kafka.session_timeout_ms,
        }

        consumer = Consumer(conf)
        consumer.subscribe([topic])
        logging.info(f"Subscribed to topic: {topic}")

        return consumer

    async def _commit_offset(self, message: Message):
        """Commit Kafka offset for a message."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.consumer.commit,
                message
            )
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

    async def _consume_loop(self):
        """Main consume loop."""
        logging.info("Starting evaluation consume loop...")

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
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logging.error(f"Kafka error: {msg.error()}")
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
        logging.info("Shutting down evaluator...")

        if self.active_tasks:
            logging.info(f"Waiting for {len(self.active_tasks)} active tasks...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.active_tasks, return_exceptions=True),
                    timeout=self.config.consumer.shutdown_grace_period_seconds
                )
            except asyncio.TimeoutError:
                for task in self.active_tasks:
                    task.cancel()

        if self.worker:
            await self.worker.close()

        if self.llm_client:
            await self.llm_client.close()

        if self.consumer:
            self.consumer.close()

        self.progress_tracker.log_final_summary()
        logging.info("Evaluator shutdown complete")

    async def run(self, topic: str = "evaluation-events"):
        """Run the consumer."""
        try:
            logging.info("Initializing evaluation consumer...")

            self.consumer = self._create_consumer(topic)
            self.llm_client = LLMClient(self.config.llm_client)
            self.worker = ConversationEvaluationWorker(
                llm_client=self.llm_client,
                config=self.config.consumer,
                commit_callback=self._commit_offset,
                results_dir=self.results_dir,
            )

            await self.worker.initialize()

            logging.info("Health check...")
            if not await self.llm_client.health_check():
                logging.error("LLM health check failed")
                sys.exit(1)

            self.running = True
            await self._consume_loop()

        except Exception as e:
            logging.error(f"Fatal error: {e}", exc_info=True)
            raise

        finally:
            await self._shutdown()


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Conversation Evaluation Consumer')
    parser.add_argument(
        '--topic',
        type=str,
        default='evaluation-events',
        help='Kafka topic to consume from'
    )
    args = parser.parse_args()

    config = Config.from_env()

    logging.info("Starting Evaluation Consumer")
    logging.info(f"Kafka: {config.kafka.bootstrap_servers}")
    logging.info(f"Topic: {args.topic}")

    consumer = EvaluationConsumer(config)
    await consumer.run(topic=args.topic)


if __name__ == "__main__":
    asyncio.run(main())
