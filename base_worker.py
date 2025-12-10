"""Base worker class with shared functionality for conversation processing."""

import asyncio
import time
import uuid
from typing import List, Optional
import aiohttp
from aiolimiter import AsyncLimiter

from config import ConsumerConfig
from llm_client import LLMClient, CircuitBreakerError
from logging_config import ConversationLogger
from schemas import (
    SimulationEvent,
    SimulatedMessageRequest,
    SimulatedMessageResponse,
    ConversationMessage,
    ConversationResult,
    TestPersona,
)

logger = ConversationLogger()


class BaseConversationWorker:
    """Base worker with shared conversation handling functionality."""

    def __init__(
        self,
        llm_client: LLMClient,
        config: ConsumerConfig,
    ):
        """
        Initialize base conversation worker.

        Args:
            llm_client: LLM client for generating responses
            config: Consumer configuration
        """
        self.llm_client = llm_client
        self.config = config

        # Concurrency control
        self.semaphore = asyncio.Semaphore(config.concurrent_conversations)

        # Rate limiting for API calls
        self.rate_limiter = AsyncLimiter(config.llm_rate_limit_rps, 1.0)

        # HTTP session for chatbot API
        self.http_session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Initialize async resources."""
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

    async def call_chatbot_simulated(
        self,
        simulation_id: str,
        conversation_id: str,
        flow_version_id: str,
        user_message: str,
        iteration: int,
        user_id: str
    ) -> SimulatedMessageResponse:
        """
        Call the /chatbot/simulated API.

        Args:
            simulation_id: Simulation ID for logging
            conversation_id: Unique conversation ID
            flow_version_id: Flow version ID
            user_message: Current user message
            iteration: Current iteration number
            user_id: User ID (test persona ID)

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
                request = SimulatedMessageRequest(
                    user_input=user_message,
                    conversation_id=conversation_id,
                    message_id=str(uuid.uuid4()),
                    flow_version_id=flow_version_id,
                    user_id=user_id,
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

    async def generate_persona_response(
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
            intent: The user's intent/purpose for the conversation

        Returns:
            Next user message
        """
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
        # Flip roles: chatbot="user" (talking to persona), persona="assistant" (persona's replies)
        messages = [{"role": "system", "content": system_prompt}]

        for msg in history:
            llm_role = "user" if msg.role == "assistant" else "assistant"
            messages.append({
                "role": llm_role,
                "content": msg.content
            })

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

    async def run_conversation(self, event: SimulationEvent) -> ConversationResult:
        """
        Run a conversation simulation.

        Args:
            event: Simulation event

        Returns:
            Conversation result
        """
        start_time = time.time()
        history: List[ConversationMessage] = []
        conversation_id = str(uuid.uuid4())
        iteration = 0
        end_reason = "max_iterations"

        try:
            async with asyncio.timeout(self.config.conversation_timeout_seconds):
                # Get initial chatbot greeting
                chatbot_response = await self.call_chatbot_simulated(
                    simulation_id=event.id,
                    conversation_id=conversation_id,
                    flow_version_id=event.flowVersionId,
                    user_message="",
                    iteration=0,
                    user_id=event.testPersona.id
                )

                greeting_text = chatbot_response.ai_response or ""
                history.append(ConversationMessage(
                    role="assistant",
                    content=greeting_text,
                    timestamp_ms=int(time.time() * 1000),
                    api_response=chatbot_response
                ))

                # Iterate: user responds, chatbot responds
                for iteration in range(1, self.config.max_iterations + 1):
                    user_message = await self.generate_persona_response(
                        simulation_id=event.id,
                        history=history,
                        persona=event.testPersona,
                        intent=event.intent
                    )

                    history.append(ConversationMessage(
                        role="user",
                        content=user_message,
                        timestamp_ms=int(time.time() * 1000)
                    ))

                    chatbot_response = await self.call_chatbot_simulated(
                        simulation_id=event.id,
                        conversation_id=conversation_id,
                        flow_version_id=event.flowVersionId,
                        user_message=user_message,
                        iteration=iteration,
                        user_id=event.testPersona.id
                    )

                    response_text = chatbot_response.ai_response or ""
                    history.append(ConversationMessage(
                        role="assistant",
                        content=response_text,
                        timestamp_ms=int(time.time() * 1000),
                        api_response=chatbot_response
                    ))

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

    def _should_end_conversation(self, chatbot_response: str, iteration: int) -> bool:
        """Check if conversation should end. Override in subclasses."""
        return False
