"""Conversation worker with rate limiting and concurrency control."""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
import aiohttp
from aiolimiter import AsyncLimiter
from pydantic import BaseModel, Field

from config import ConsumerConfig
from llm_client import LLMClient, CircuitBreakerError
from logging_config import ConversationLogger

logger = ConversationLogger()


# ============================================================================
# Event Schema (from Kafka)
# ============================================================================

class FieldValue(BaseModel):
    """Field value for persona."""
    id: str
    testPersonaId: str
    fieldName: str
    fieldValue: str


class TestPersona(BaseModel):
    """Test persona from event."""
    id: str
    name: str
    description: str
    fieldValues: List[FieldValue] = Field(default_factory=list)


class SimulationEvent(BaseModel):
    """Simulation event from Kafka."""
    id: str
    flowVersionId: str
    testGoal: str
    intent: str
    testPersona: TestPersona


# ============================================================================
# Chatbot API Schema (Request/Response)
# ============================================================================

class SimulatedMessageRequest(BaseModel):
    """Request payload for /chatbot/simulated endpoint."""
    user_input: str
    conversation_id: str
    message_id: str
    flow_version_id: Optional[str] = None
    flow_deployment_id: Optional[str] = None
    product: Optional[str] = None
    language: str = "english"
    file_urls: List[str] = Field(default_factory=list)
    is_question_input: bool = False
    is_streaming_enabled: bool = False
    chat_source: str = "EMBEDDED"
    user_id: str  # Required for simulated endpoint


class APICallRecord(BaseModel):
    """Record of an API call made during processing."""
    url: str
    method: str


class ErrorRecord(BaseModel):
    """Record of an error during processing."""
    error_type: str
    message: str


class ExtraMessageData(BaseModel):
    """Extra data returned from simulated endpoint."""
    num_turns: Optional[int] = None
    node_path: List[str] = Field(default_factory=list)
    latency: Optional[float] = None
    api_calls_made: Optional[List[APICallRecord]] = None
    errors: Optional[List[ErrorRecord]] = None


class ChatButtons(BaseModel):
    """Chat button options."""
    buttons: List[str] = Field(default_factory=list)


class SimulatedMessageResponse(BaseModel):
    """Response from /chatbot/simulated endpoint."""
    ai_response: Optional[str] = None
    ai_response_files: List[str] = Field(default_factory=list)
    ai_response_id: Optional[str] = None
    chat_buttons: Optional[ChatButtons] = None
    chat_status: Optional[str] = None
    upload_enabled: bool = False
    bot_lead: Optional[Dict[str, str]] = None
    response_time: Optional[float] = None
    post_message_data: Optional[List[Dict[str, Any]]] = None
    node_id: Optional[str] = None
    extra_data: Optional[ExtraMessageData] = None


# ============================================================================
# Conversation Data
# ============================================================================

class ConversationMessage(BaseModel):
    """A single message in the conversation."""
    role: str  # "user" or "assistant" (chatbot)
    content: str
    timestamp_ms: int
    api_response: Optional[SimulatedMessageResponse] = None  # Full API response for assistant messages


class ConversationResult(BaseModel):
    """Result to POST after conversation completion."""
    simulation_id: str
    flow_version_id: str
    test_goal: str
    test_persona_id: str
    conversation_history: List[ConversationMessage]
    total_iterations: int
    end_reason: str  # completed, max_iterations, timeout, goal_reached
    goal_reached: bool
    duration_ms: int


# ============================================================================
# Worker
# ============================================================================

class ConversationWorker:
    """Worker that handles conversations with rate limiting."""

    def __init__(
        self,
        llm_client: LLMClient,
        config: ConsumerConfig,
        commit_callback
    ):
        """
        Initialize conversation worker.

        Args:
            llm_client: LLM client for generating persona responses
            config: Consumer configuration
            commit_callback: Async function to call for committing Kafka offset
        """
        self.llm_client = llm_client
        self.config = config
        self.commit_callback = commit_callback

        # Concurrency control
        self.semaphore = asyncio.Semaphore(config.concurrent_conversations)

        # Rate limiting for API calls
        self.rate_limiter = AsyncLimiter(config.llm_rate_limit_rps, 1.0)

        # HTTP session for chatbot API and posting results
        self.http_session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Initialize async resources."""
        # Build headers with JWT auth if configured
        headers = {}
        if self.config.agent_jwt_token:
            headers["Authorization"] = f"Bearer {self.config.agent_jwt_token}"

        self.http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers=headers
        )

    async def close(self):
        """Close async resources."""
        if self.http_session:
            await self.http_session.close()

    async def process_event(self, event_data: Dict[str, Any], kafka_message):
        """
        Process a single simulation event.

        Args:
            event_data: Event data dictionary
            kafka_message: Kafka message object (for committing offset)
        """
        async with self.semaphore:
            start_time = time.time()
            simulation_id = event_data.get('id', 'unknown')

            try:
                # Parse event
                event = SimulationEvent(**event_data)

                logger.conversation_started(
                    simulation_id=event.id,
                    persona_name=event.testPersona.name,
                    test_goal=event.testGoal
                )

                # Run conversation
                result = await self._run_conversation(event)

                # Save result
                await self._post_result(result)

                # Commit Kafka offset
                await self.commit_callback(kafka_message)

                # Log completion
                duration = time.time() - start_time
                logger.conversation_completed(
                    simulation_id=event.id,
                    iterations=result.total_iterations,
                    duration_ms=int(duration * 1000),
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

    async def _run_conversation(self, event: SimulationEvent) -> ConversationResult:
        """
        Run a conversation simulation.

        Flow:
        1. Call /chatbot/simulated with empty message to get chatbot greeting
        2. Generate user response using LLM (based on persona and intent)
        3. Send user message to chatbot, get response
        4. Repeat until max iterations or conversation ends

        Args:
            event: Simulation event

        Returns:
            Conversation result
        """
        start_time = time.time()
        history: List[ConversationMessage] = []

        # Generate unique conversation ID for this simulation
        conversation_id = str(uuid.uuid4())

        iteration = 0
        end_reason = "max_iterations"

        try:
            async with asyncio.timeout(self.config.conversation_timeout_seconds):
                # Get initial chatbot greeting (iteration 0)
                chatbot_response = await self._call_chatbot_simulated(
                    simulation_id=event.id,
                    conversation_id=conversation_id,
                    flow_version_id=event.flowVersionId,
                    user_message="",  # Empty message to trigger greeting
                    iteration=0
                )

                # Record chatbot greeting
                greeting_text = chatbot_response.ai_response or ""
                history.append(ConversationMessage(
                    role="assistant",
                    content=greeting_text,
                    timestamp_ms=int(time.time() * 1000),
                    api_response=chatbot_response
                ))

                # Now iterate: user responds, chatbot responds
                for iteration in range(1, self.config.max_iterations + 1):
                    # Generate user message based on persona and intent
                    user_message = await self._generate_persona_response(
                        simulation_id=event.id,
                        history=history,
                        persona=event.testPersona,
                        intent=event.intent
                    )

                    # Check if persona wants to end
                    if "[END_CONVERSATION]" in user_message:
                        end_reason = "completed"
                        break

                    # Record user message
                    history.append(ConversationMessage(
                        role="user",
                        content=user_message,
                        timestamp_ms=int(time.time() * 1000)
                    ))

                    # Call chatbot simulated API
                    chatbot_response = await self._call_chatbot_simulated(
                        simulation_id=event.id,
                        conversation_id=conversation_id,
                        flow_version_id=event.flowVersionId,
                        user_message=user_message,
                        iteration=iteration
                    )

                    # Extract response text and extra data
                    response_text = chatbot_response.ai_response or ""

                    # Record chatbot response with full API response
                    history.append(ConversationMessage(
                        role="assistant",
                        content=response_text,
                        timestamp_ms=int(time.time() * 1000),
                        api_response=chatbot_response
                    ))

                    # Check if conversation should end naturally
                    if self._should_end_conversation(response_text, iteration):
                        end_reason = "completed"
                        break

        except asyncio.TimeoutError:
            end_reason = "timeout"
            logger.conversation_failed(
                simulation_id=event.id,
                error="timeout",
                iteration=iteration
            )

        duration_ms = int((time.time() - start_time) * 1000)

        return ConversationResult(
            simulation_id=event.id,
            flow_version_id=event.flowVersionId,
            test_goal=event.testGoal,
            test_persona_id=event.testPersona.id,
            conversation_history=history,
            total_iterations=iteration,
            end_reason=end_reason,
            goal_reached=False,
            duration_ms=duration_ms
        )

    async def _call_chatbot_simulated(
        self,
        simulation_id: str,
        conversation_id: str,
        flow_version_id: str,
        user_message: str,
        iteration: int
    ) -> SimulatedMessageResponse:
        """
        Call the /chatbot/simulated API.

        Args:
            simulation_id: Simulation ID for logging
            conversation_id: Unique conversation ID
            flow_version_id: Flow version ID
            user_message: Current user message
            iteration: Current iteration number

        Returns:
            SimulatedMessageResponse with chatbot response and extra data
        """
        async with self.rate_limiter:
            start_time = time.time()

            logger.chatbot_request(
                simulation_id=simulation_id,
                iteration=iteration,
                message_preview=user_message
            )

            try:
                # Build request payload using proper schema
                request = SimulatedMessageRequest(
                    user_input=user_message,
                    conversation_id=conversation_id,
                    message_id=str(uuid.uuid4()),
                    flow_version_id=flow_version_id,
                    user_id=f"{simulation_id}",
                    language="english",
                    is_streaming_enabled=False,
                    chat_source="EMBEDDED"
                )

                async with self.http_session.post(
                    self.config.chatbot_simulated_url,
                    json=request.model_dump(exclude_none=True),
                    timeout=aiohttp.ClientTimeout(total=self.config.chatbot_timeout_seconds)
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                    latency_ms = int((time.time() - start_time) * 1000)

                    # Parse response using schema
                    chatbot_response = SimulatedMessageResponse(**data)
                    response_text = chatbot_response.ai_response or ""

                    logger.chatbot_response(
                        simulation_id=simulation_id,
                        iteration=iteration,
                        latency_ms=latency_ms,
                        response_preview=response_text
                    )

                    return chatbot_response

            except aiohttp.ClientResponseError as e:
                logger.llm_error(
                    simulation_id=simulation_id,
                    error=f"HTTP {e.status}",
                    attempt=1
                )
                raise

            except asyncio.TimeoutError:
                logger.llm_error(
                    simulation_id=simulation_id,
                    error="timeout",
                    attempt=1
                )
                raise

            except Exception as e:
                logger.llm_error(
                    simulation_id=simulation_id,
                    error=str(e),
                    attempt=1
                )
                raise

    async def _generate_persona_response(
        self,
        simulation_id: str,
        history: List[ConversationMessage],
        persona: TestPersona,
        intent: str = ""
    ) -> str:
        """
        Generate the next user message based on persona using LLM.

        Args:
            simulation_id: Simulation ID for logging
            history: Conversation history
            persona: Test persona
            test_goal: Goal the persona is trying to achieve
            intent: The user's intent/purpose for the conversation

        Returns:
            Next user message
        """
        # Build persona description from fieldValues
        field_info = "\n".join(
            f"- {fv.fieldName}: {fv.fieldValue}"
            for fv in persona.fieldValues
        )

        system_prompt = f"""You are simulating a user in a conversation with a chatbot.

USER PERSONA:
Name: {persona.name}
Description: {persona.description}
{f"Details:{chr(10)}{field_info}" if field_info else ""}

USER'S INTENT:
{intent}

INSTRUCTIONS:
- Generate the next message this user would send to the chatbot
- Stay in character based on the persona
- Keep responses concise (1-3 sentences)
- Do NOT break character or mention that you are simulating"""

        # Build conversation context for LLM
        # IMPORTANT: Flip roles for the LLM perspective
        # - Chatbot messages (assistant) -> appear as "user" to LLM (someone talking TO the persona)
        # - Persona messages (user) -> appear as "assistant" to LLM (what the persona said)
        messages = [{"role": "system", "content": system_prompt}]

        for msg in history:
            # Flip: chatbot="user" (talking to persona), persona="assistant" (persona's replies)
            llm_role = "user" if msg.role == "assistant" else "assistant"
            messages.append({
                "role": llm_role,
                "content": msg.content
            })

        # Call LLM
        async with self.rate_limiter:
            logger.llm_request(
                simulation_id=simulation_id,
                model=self.config.persona_llm_model,
                purpose="generate_persona_response"
            )

            start_time = time.time()

            try:
                response = await self.llm_client.chat_completion(
                    messages=messages,
                    model=self.config.persona_llm_model,
                    temperature=1
                )

                latency_ms = int((time.time() - start_time) * 1000)
                logger.llm_response(
                    simulation_id=simulation_id,
                    latency_ms=latency_ms
                )

                return response.strip()

            except CircuitBreakerError:
                logger.llm_error(
                    simulation_id=simulation_id,
                    error="circuit_breaker_open",
                    attempt=1
                )
                raise

            except Exception as e:
                logger.llm_error(
                    simulation_id=simulation_id,
                    error=str(e),
                    attempt=1
                )
                raise

    def _should_end_conversation(self, chatbot_response: str, iteration: int) -> bool:
        """
        Determine if conversation should end based on chatbot response.

        Args:
            chatbot_response: Last chatbot response
            iteration: Current iteration

        Returns:
            True if conversation should end
        """
        # Check for common ending patterns in chatbot response
        ending_phrases = [
            "goodbye",
            "have a great day",
            "is there anything else",
            "glad i could help",
            "thank you for contacting",
        ]

        response_lower = chatbot_response.lower()
        for phrase in ending_phrases:
            if phrase in response_lower:
                return True

        return False

    async def _post_result(self, result: ConversationResult):
        """
        Save result to local file (for testing) instead of POSTing to callback URL.

        Args:
            result: Conversation result
        """
        try:
            # Create results directory if it doesn't exist
            results_dir = Path("results")
            results_dir.mkdir(exist_ok=True)

            # Write result to file
            output_file = results_dir / f"result_{result.simulation_id}.json"
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
