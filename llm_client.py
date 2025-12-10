"""LLM client using LiteLLM with connection pooling, retry logic, and circuit breaker."""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from litellm import acompletion
from litellm.exceptions import RateLimitError, ServiceUnavailableError, Timeout
from config import LLMClientConfig

logger = logging.getLogger(__name__)


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """Circuit breaker pattern implementation."""

    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timedelta(seconds=timeout_seconds)
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"  # closed, open, half_open

    def record_success(self):
        """Record a successful call."""
        self.failure_count = 0
        self.state = "closed"

    def record_failure(self):
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")

    def can_attempt(self) -> bool:
        """Check if a call can be attempted."""
        if self.state == "closed":
            return True

        if self.state == "open":
            if datetime.utcnow() - self.last_failure_time > self.timeout:
                self.state = "half_open"
                logger.info("Circuit breaker entering half-open state")
                return True
            return False

        # half_open state
        return True


class LLMClient:
    """Async LLM client using LiteLLM with retry logic."""

    def __init__(self, config: LLMClientConfig):
        self.config = config
        self.circuit_breaker = CircuitBreaker()

    async def close(self):
        """Close the client (no-op for LiteLLM, kept for interface compatibility)."""
        pass

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Make a chat completion request with retry logic using LiteLLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name to use (supports any LiteLLM model format, e.g.,
                   'gpt-4', 'claude-3-opus', 'bedrock/anthropic.claude-v2', etc.)
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters to pass to LiteLLM

        Returns:
            The assistant's response content

        Raises:
            CircuitBreakerError: If circuit breaker is open
            Exception: If all retry attempts fail
        """
        if not self.circuit_breaker.can_attempt():
            raise CircuitBreakerError("Circuit breaker is open, LLM backend unavailable")

        for attempt in range(self.config.retry_attempts):
            try:
                response = await self._make_request(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs
                )

                self.circuit_breaker.record_success()
                return response

            except RateLimitError as e:
                backoff_time = min(2 ** attempt, 16)  # Max 16 seconds
                logger.warning(
                    f"Rate limited, backing off {backoff_time}s "
                    f"(attempt {attempt + 1}/{self.config.retry_attempts}): {e}"
                )
                await asyncio.sleep(backoff_time)
                continue

            except (ServiceUnavailableError, Timeout) as e:
                self.circuit_breaker.record_failure()
                if attempt < self.config.retry_attempts - 1:
                    backoff_time = 2 ** attempt
                    logger.warning(
                        f"Service error, retrying in {backoff_time}s "
                        f"(attempt {attempt + 1}/{self.config.retry_attempts}): {e}"
                    )
                    await asyncio.sleep(backoff_time)
                    continue
                raise

            except Exception as e:
                self.circuit_breaker.record_failure()
                if attempt < self.config.retry_attempts - 1:
                    backoff_time = 2 ** attempt
                    logger.warning(
                        f"Request failed: {e}, retrying in {backoff_time}s "
                        f"(attempt {attempt + 1}/{self.config.retry_attempts})"
                    )
                    await asyncio.sleep(backoff_time)
                    continue
                raise

        raise Exception(f"Failed after {self.config.retry_attempts} attempts")

    async def _make_request(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        **kwargs
    ) -> str:
        """Make a single API request using LiteLLM."""
        request_kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "timeout": self.config.timeout_seconds,
        }

        if max_tokens:
            request_kwargs["max_tokens"] = max_tokens

        # Check if using Azure OpenAI (model starts with "azure/")
        if model.startswith("azure/"):
            if self.config.azure_api_key:
                request_kwargs["api_key"] = self.config.azure_api_key
            if self.config.azure_api_base:
                request_kwargs["api_base"] = self.config.azure_api_base
            if self.config.azure_api_version:
                request_kwargs["api_version"] = self.config.azure_api_version
        else:
            # Standard OpenAI or other providers
            if self.config.api_key:
                request_kwargs["api_key"] = self.config.api_key

        # Merge any additional kwargs
        request_kwargs.update(kwargs)

        # Use LiteLLM's async completion
        response = await acompletion(**request_kwargs)

        # Extract content from response
        return response.choices[0].message.content

    async def health_check(self, model: str = "gpt-3.5-turbo") -> bool:
        """Check if the LLM backend is healthy."""
        try:
            # Simple health check with minimal message
            await self.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                model=model,
                max_tokens=5
            )
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
