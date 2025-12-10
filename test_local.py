#!/usr/bin/env python3
"""
Local test script to run conversation simulation without Kafka.

Usage:
    python test_local.py

This script:
1. Creates a mock event (or loads from file)
2. Runs the conversation worker directly
3. Prints the results (doesn't POST to callback)

Requirements:
- Set environment variables (or create .env file)
- Agent backend must be running (AGENT_URL)
- LLM API key must be set (LLM_API_KEY)
"""

import asyncio
import json
import logging
from dotenv import load_dotenv

# Load .env file if exists
load_dotenv()

from config import Config
from llm_client import LLMClient
from worker import (
    ConversationWorker,
    SimulationEvent,
    TestPersona,
    FieldValue,
    ConversationResult
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Sample test event
SAMPLE_EVENT = {
    "id": "875454ae-50ec-4f5c-92c5-b049f5355e11",
    "flowVersionId": "ca46945d-86d4-4a05-857d-d89c9fab943c",
    "testGoal": "User got a loan",
    "intent": "Take a loan",
    "testPersona": {
        "id": "875454ae-50ec-4f5c-92c5-b049f5355e11",
        "name": "David",
        "description": "developer",
        "fieldValues": [
            {
                "id": "95dadd2b-26eb-441b-8e39-3c91bb66464e",
                "testPersonaId": "875454ae-50ec-4f5c-92c5-b049f5355e11",
                "fieldName": "age",
                "fieldValue": "27"
            },
            {
                "id": "0efe3ff7-ad1e-4bad-befd-e26a0f5ec29d",
                "testPersonaId": "875454ae-50ec-4f5c-92c5-b049f5355e11",
                "fieldName": "field",
                "fieldValue": "full stack"
            }
        ]
    }
}


class LocalTestWorker(ConversationWorker):
    """Worker modified for local testing - skips Kafka commit and result POST."""

    async def process_event_local(self, event_data: dict) -> ConversationResult:
        """
        Process event locally without Kafka commit or result POST.

        Args:
            event_data: Event data dictionary

        Returns:
            ConversationResult
        """
        # Parse event
        event = SimulationEvent(**event_data)
        logger.info(f"Processing event: {event.id}")
        logger.info(f"Persona: {event.testPersona.name} - {event.testPersona.description}")
        logger.info(f"Goal: {event.testGoal}")
        logger.info(f"Intent: {event.intent}")

        # Run conversation
        result = await self._run_conversation(event)

        return result


async def run_local_test(event_data: dict, dry_run: bool = False, max_iterations: int = None):
    """
    Run a local test of the conversation worker.

    Args:
        event_data: Event to process
        dry_run: If True, skip actual API calls (mock responses)
        max_iterations: Override max iterations (optional)
    """
    config = Config.from_env()

    # Override max_iterations if specified
    if max_iterations is not None:
        config.consumer.max_iterations = max_iterations

    logger.info("=" * 60)
    logger.info("LOCAL TEST - Configuration")
    logger.info("=" * 60)
    logger.info(f"Agent URL: {config.consumer.agent_url}:{config.consumer.agent_port}")
    logger.info(f"Chatbot URL: {config.consumer.chatbot_simulated_url}")
    logger.info(f"JWT Token: {'SET' if config.consumer.agent_jwt_token else 'NOT SET'}")
    logger.info(f"LLM Model: {config.consumer.persona_llm_model}")
    logger.info(f"LLM API Key: {'SET' if config.llm_client.api_key else 'NOT SET'}")
    logger.info(f"Max Iterations: {config.consumer.max_iterations}")
    logger.info("=" * 60)

    if not config.consumer.agent_jwt_token:
        logger.warning("AGENT_JWT_TOKEN not set - API calls may fail")

    if not config.llm_client.api_key:
        logger.warning("LLM_API_KEY not set - persona generation will fail")

    # Initialize components
    llm_client = LLMClient(config.llm_client)

    # Dummy commit callback (not used in local test)
    async def dummy_commit(msg):
        pass

    worker = LocalTestWorker(
        llm_client=llm_client,
        config=config.consumer,
        commit_callback=dummy_commit
    )

    await worker.initialize()

    try:
        logger.info("\n" + "=" * 60)
        logger.info("Starting conversation...")
        logger.info("=" * 60 + "\n")

        result = await worker.process_event_local(event_data)

        # Print results
        logger.info("\n" + "=" * 60)
        logger.info("CONVERSATION RESULT")
        logger.info("=" * 60)
        logger.info(f"Simulation ID: {result.simulation_id}")
        logger.info(f"Total Iterations: {result.total_iterations}")
        logger.info(f"End Reason: {result.end_reason}")
        logger.info(f"Goal Reached: {result.goal_reached}")
        logger.info(f"Duration: {result.duration_ms}ms")

        logger.info("\n" + "-" * 60)
        logger.info("CONVERSATION HISTORY")
        logger.info("-" * 60)

        for i, msg in enumerate(result.conversation_history):
            role_label = "USER" if msg.role == "user" else "BOT "
            logger.info(f"\n[{i+1}] {role_label}: {msg.content[:200]}{'...' if len(msg.content) > 200 else ''}")

        logger.info("\n" + "=" * 60)

        # Save full result to file
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"t_result_{timestamp}.json"
        with open(output_file, 'w') as f:
            json.dump(result.model_dump(), f, indent=2)
        logger.info(f"Full result saved to: {output_file}")

        return result

    finally:
        await worker.close()
        await llm_client.close()


async def run_mock_test(event_data: dict):
    """
    Run a mock test without any API calls.
    Useful for testing the flow logic.
    """
    logger.info("=" * 60)
    logger.info("MOCK TEST - No API calls")
    logger.info("=" * 60)

    event = SimulationEvent(**event_data)

    logger.info(f"Event ID: {event.id}")
    logger.info(f"Flow Version: {event.flowVersionId}")
    logger.info(f"Test Goal: {event.testGoal}")
    logger.info(f"Intent: {event.intent}")
    logger.info(f"Persona: {event.testPersona.name}")
    logger.info(f"Description: {event.testPersona.description}")

    logger.info("\nField Values:")
    for fv in event.testPersona.fieldValues:
        logger.info(f"  - {fv.fieldName}: {fv.fieldValue}")

    logger.info("\n✓ Event parsed successfully")
    logger.info("✓ Schema validation passed")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Local test for conversation consumer')
    parser.add_argument(
        '--event-file',
        type=str,
        help='JSON file containing event data (default: use sample event)'
    )
    parser.add_argument(
        '--mock',
        action='store_true',
        help='Run mock test without API calls (validates event schema only)'
    )
    parser.add_argument(
        '--max-iterations',
        type=int,
        help='Override max iterations'
    )

    args = parser.parse_args()

    # Load event data
    if args.event_file:
        with open(args.event_file) as f:
            event_data = json.load(f)
        logger.info(f"Loaded event from: {args.event_file}")
    else:
        event_data = SAMPLE_EVENT
        logger.info("Using sample event")

    # Run test
    if args.mock:
        asyncio.run(run_mock_test(event_data))
    else:
        asyncio.run(run_local_test(event_data, max_iterations=args.max_iterations))


if __name__ == '__main__':
    main()
