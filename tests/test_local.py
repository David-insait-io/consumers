#!/usr/bin/env python3
"""
Local test script to run conversation simulation and evaluation without Kafka.

Usage:
    python test_local.py                          # Run first sample event
    python test_local.py --event loan             # Run specific event by name
    python test_local.py --event all              # Run all events
    python test_local.py --count 10               # Run first 10 events
    python test_local.py --event-file event.json  # Load from file
    python test_local.py --list                   # List available events
    python test_local.py --max-iterations 3       # Override iterations
    python test_local.py --parallel               # Run tests in parallel
    python test_local.py --evaluate               # Also evaluate goal achievement

Requirements:
- Set environment variables (or create .env file)
- Agent backend must be running (AGENT_URL)
- LLM API key must be set (LLM_API_KEY)
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from config import Config
from llm_client import LLMClient
from base_worker import BaseConversationWorker
from schemas import SimulationEvent, ConversationResult, EvaluationResult
from sample_events import SAMPLE_EVENTS, get_events

# Results directory
RESULTS_DIR = Path(__file__).parent / "results"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def list_events():
    """Print available sample events."""
    print("\nAvailable sample events:")
    print("-" * 60)
    for name, event in SAMPLE_EVENTS.items():
        persona = event["testPersona"]
        print(f"\n  {name}:")
        print(f"    Persona: {persona['name']} - {persona['description'][:50]}...")
        print(f"    Intent: {event['intent'][:50]}...")
        print(f"    Goal: {event['testGoal'][:50]}...")
    print()


# ============================================================================
# Test Worker
# ============================================================================

class LocalTestWorker(BaseConversationWorker):
    """Worker for local testing - no Kafka commit needed."""

    async def process_event_local(self, event_data: dict) -> ConversationResult:
        """
        Process event locally without Kafka commit.

        Args:
            event_data: Event data dictionary

        Returns:
            ConversationResult
        """
        event = SimulationEvent(**event_data)
        logger.info(f"Processing event: {event.id}")
        logger.info(f"Persona: {event.testPersona.name} - {event.testPersona.description}")
        logger.info(f"Goal: {event.testGoal}")
        logger.info(f"Intent: {event.intent}")

        result = await self.run_conversation(event)
        return result


class LocalEvaluationWorker(BaseConversationWorker):
    """Worker for evaluating conversation goal achievement."""

    async def evaluate_goal(
        self,
        conversation_result: ConversationResult
    ) -> EvaluationResult:
        """
        Evaluate if a conversation achieved its test goal.

        Args:
            conversation_result: The conversation to evaluate

        Returns:
            EvaluationResult
        """
        import time
        start_time = time.time()

        # Build transcript
        transcript = self._build_transcript(conversation_result.conversation_history)

        # Evaluate goal
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

    def _build_transcript(self, history) -> str:
        """Build readable transcript."""
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
    ) -> tuple:
        """Evaluate if the test goal was achieved."""
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
            try:
                response = await self.llm_client.chat_completion(
                    messages=messages,
                    model=self.config.persona_llm_model,
                    temperature=1
                )

                result = json.loads(response.strip())
                return (
                    bool(result.get("goal_achieved", False)),
                    result.get("reasoning", "No reasoning provided")
                )

            except json.JSONDecodeError:
                return False, f"Failed to parse response: {response[:100]}"
            except Exception as e:
                return False, f"Evaluation error: {str(e)}"


# ============================================================================
# Test Runner
# ============================================================================

async def run_single_test(
    worker: LocalTestWorker,
    event_data: dict,
    event_name: str = "unknown",
    evaluator: Optional[LocalEvaluationWorker] = None
) -> dict:
    """Run a single conversation test."""
    logger.info("\n" + "=" * 60)
    logger.info(f"RUNNING TEST: {event_name}")
    logger.info("=" * 60)

    result = await worker.process_event_local(event_data)

    # Print summary
    logger.info("\n" + "-" * 60)
    logger.info("RESULT SUMMARY")
    logger.info("-" * 60)
    logger.info(f"Simulation ID: {result.simulation_id}")
    logger.info(f"Total Iterations: {result.total_iterations}")
    logger.info(f"End Reason: {result.end_reason}")
    logger.info(f"Duration: {result.duration_ms}ms")

    logger.info("\nCONVERSATION:")
    for i, msg in enumerate(result.conversation_history):
        role_label = "USER" if msg.role == "user" else "BOT "
        content_preview = msg.content[:150] + "..." if len(msg.content) > 150 else msg.content
        logger.info(f"  [{i+1}] {role_label}: {content_preview}")

    # Evaluate if requested
    evaluation = None
    if evaluator:
        logger.info("\n" + "-" * 60)
        logger.info("EVALUATING GOAL ACHIEVEMENT...")
        logger.info("-" * 60)
        evaluation = await evaluator.evaluate_goal(result)
        status = "ACHIEVED" if evaluation.goal_achieved else "NOT ACHIEVED"
        logger.info(f"Goal: {status}")
        logger.info(f"Reasoning: {evaluation.reasoning}")

    return {"result": result, "evaluation": evaluation}


async def run_tests(
    events: List[tuple],
    max_iterations: Optional[int] = None,
    parallel: bool = False,
    evaluate: bool = False
):
    """
    Run multiple conversation tests.

    Args:
        events: List of (event_name, event_data) tuples
        max_iterations: Override max iterations
        parallel: Run tests in parallel
        evaluate: Also evaluate goal achievement
    """
    config = Config.from_env()

    if max_iterations is not None:
        config.consumer.max_iterations = max_iterations

    # Print configuration
    logger.info("=" * 60)
    logger.info("TEST CONFIGURATION")
    logger.info("=" * 60)
    logger.info(f"Chatbot URL: {config.consumer.chatbot_simulated_url}")
    logger.info(f"LLM Model: {config.consumer.persona_llm_model}")
    logger.info(f"Max Iterations: {config.consumer.max_iterations}")
    logger.info(f"Number of tests: {len(events)}")
    logger.info(f"Mode: {'parallel' if parallel else 'sequential'}")
    logger.info(f"Evaluate: {evaluate}")
    logger.info("=" * 60)

    # Initialize components
    llm_client = LLMClient(config.llm_client)

    worker = LocalTestWorker(
        llm_client=llm_client,
        config=config.consumer,
    )
    await worker.initialize()

    evaluator = None
    if evaluate:
        evaluator = LocalEvaluationWorker(
            llm_client=llm_client,
            config=config.consumer,
        )
        await evaluator.initialize()

    results = []
    start_time = datetime.now()

    try:
        if parallel:
            tasks = [
                run_single_test(worker, event_data, event_name, evaluator)
                for event_name, event_data in events
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            for event_name, event_data in events:
                try:
                    result = await run_single_test(worker, event_data, event_name, evaluator)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Test '{event_name}' failed: {e}")
                    results.append(e)

        # Calculate total time
        total_seconds = (datetime.now() - start_time).total_seconds()

        # Save results
        RESULTS_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = RESULTS_DIR / f"t_result_{timestamp}.json"

        successful_results = [r for r in results if isinstance(r, dict)]

        # Build output data
        output_data = {
            "timestamp": timestamp,
            "total_tests": len(events),
            "successful": len(successful_results),
            "failed": len(events) - len(successful_results),
            "total_duration_seconds": total_seconds,
            "results": []
        }

        for r in successful_results:
            result_data = r["result"].model_dump()
            if r.get("evaluation"):
                result_data["evaluation"] = {
                    "goal_achieved": r["evaluation"].goal_achieved,
                    "reasoning": r["evaluation"].reasoning,
                    "duration_ms": r["evaluation"].duration_ms
                }
            output_data["results"].append(result_data)

        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

        # Print final summary
        logger.info("\n" + "=" * 60)
        logger.info("FINAL SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total tests: {len(events)}")
        logger.info(f"Successful: {len(successful_results)}")
        logger.info(f"Failed: {len(events) - len(successful_results)}")
        logger.info(f"Total time: {total_seconds:.2f}s")

        if evaluate:
            achieved = sum(1 for r in successful_results if r.get("evaluation") and r["evaluation"].goal_achieved)
            logger.info(f"Goals achieved: {achieved}/{len(successful_results)}")

        logger.info(f"Results saved to: {output_file}")
        logger.info("=" * 60)

        return results

    finally:
        await worker.close()
        if evaluator:
            await evaluator.close()
        await llm_client.close()


async def run_mock_test(event_data: dict):
    """Run a mock test without any API calls."""
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

    logger.info("\n Event parsed successfully")
    logger.info(" Schema validation passed")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Local test for conversation simulation')
    parser.add_argument(
        '--event',
        type=str,
        nargs='*',
        help='Event name(s) to run (e.g., home_renovation). Use "all" for all events.'
    )
    parser.add_argument(
        '--event-file',
        type=str,
        help='JSON file containing event data'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available sample events'
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
    parser.add_argument(
        '--parallel',
        action='store_true',
        help='Run multiple tests in parallel'
    )
    parser.add_argument(
        '--count',
        type=int,
        help='Number of sample events to run (default: all 30)'
    )
    parser.add_argument(
        '--evaluate',
        action='store_true',
        help='Evaluate if test goals were achieved'
    )

    args = parser.parse_args()

    # List events
    if args.list:
        list_events()
        return

    # Determine which events to run
    events_to_run = []

    if args.event_file:
        with open(args.event_file) as f:
            data = json.load(f)
        if isinstance(data, list):
            for i, event in enumerate(data):
                events_to_run.append((f"file_event_{i}", event))
        else:
            events_to_run.append(("file_event", data))
        logger.info(f"Loaded {len(events_to_run)} event(s) from: {args.event_file}")

    elif args.event:
        if "all" in args.event:
            events_to_run = [(name, event) for name, event in SAMPLE_EVENTS.items()]
        else:
            for name in args.event:
                if name in SAMPLE_EVENTS:
                    events_to_run.append((name, SAMPLE_EVENTS[name]))
                else:
                    logger.error(f"Unknown event: {name}. Use --list to see available events.")
                    return
    elif args.count:
        selected_events = get_events(args.count)
        events_to_run = [(name, event) for name, event in selected_events.items()]
        logger.info(f"Running {len(events_to_run)} events (--count {args.count})")
    else:
        first_name = list(SAMPLE_EVENTS.keys())[0]
        events_to_run.append((first_name, SAMPLE_EVENTS[first_name]))
        logger.info(f"Using default event: {first_name}")

    # Run tests
    if args.mock:
        for name, event in events_to_run:
            asyncio.run(run_mock_test(event))
    else:
        asyncio.run(run_tests(
            events_to_run,
            max_iterations=args.max_iterations,
            parallel=args.parallel,
            evaluate=args.evaluate
        ))


if __name__ == '__main__':
    main()
