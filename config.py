"""Configuration management for the simulation consumer."""

from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class KafkaConfig:
    """Kafka configuration."""
    bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    topic: str = os.getenv("KAFKA_TOPIC", "simulation-events")
    consumer_group: str = os.getenv("KAFKA_CONSUMER_GROUP", "simulation-consumer-group")
    auto_commit: bool = False
    max_poll_interval_ms: int = 600000  # 10 minutes
    session_timeout_ms: int = 30000
    max_poll_records: int = 100


@dataclass
class ConsumerConfig:
    """Consumer behavior configuration."""
    concurrent_conversations: int = int(os.getenv("CONCURRENT_CONVERSATIONS", "20"))
    llm_rate_limit_rps: int = int(os.getenv("LLM_RATE_LIMIT_RPS", "10"))
    max_iterations: int = int(os.getenv("MAX_ITERATIONS", "10"))
    conversation_timeout_seconds: int = int(os.getenv("CONVERSATION_TIMEOUT", "300"))
    shutdown_grace_period_seconds: int = 60

    # Agent backend configuration
    agent_url: str = os.getenv("AGENT_URL", "http://agent-backend")
    agent_port: int = int(os.getenv("AGENT_PORT", "5000"))
    agent_jwt_token: Optional[str] = os.getenv("AGENT_JWT_TOKEN")
    chatbot_timeout_seconds: int = int(os.getenv("CHATBOT_TIMEOUT", "30"))

    # Results callback API
    results_callback_url: str = os.getenv("RESULTS_CALLBACK_URL", "http://localhost:8080/simulations/results")

    # LLM model for persona response generation
    persona_llm_model: str = os.getenv("PERSONA_LLM_MODEL", "gpt-4")

    @property
    def chatbot_simulated_url(self) -> str:
        """Build the chatbot simulated URL from agent config."""
        return f"{self.agent_url}:{self.agent_port}/chatbot/simulated"


@dataclass
class LLMClientConfig:
    """LLM client configuration for persona response generation."""
    timeout_seconds: int = int(os.getenv("LLM_TIMEOUT", "30"))
    retry_attempts: int = int(os.getenv("LLM_RETRY_ATTEMPTS", "3"))

    # Standard OpenAI
    api_key: Optional[str] = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")

    # Azure OpenAI (optional - LiteLLM reads these automatically)
    azure_api_key: Optional[str] = os.getenv("AZURE_API_KEY") or os.getenv("OPENAI_API_KEY")
    azure_api_base: Optional[str] = os.getenv("AZURE_API_BASE") or os.getenv("OPENAI_API_BASE")
    azure_api_version: Optional[str] = os.getenv("AZURE_API_VERSION") or os.getenv("OPENAI_API_VERSION")


@dataclass
class Config:
    """Main configuration container."""
    kafka: KafkaConfig
    consumer: ConsumerConfig
    llm_client: LLMClientConfig

    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables."""
        return cls(
            kafka=KafkaConfig(),
            consumer=ConsumerConfig(),
            llm_client=LLMClientConfig()
        )
