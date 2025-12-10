"""Shared Pydantic schemas for conversation simulation and evaluation."""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


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
    """Result from conversation simulation."""
    simulation_id: str
    flow_version_id: str
    test_goal: str
    test_persona_id: str
    conversation_history: List[ConversationMessage]
    total_iterations: int
    end_reason: str  # completed, max_iterations, timeout
    goal_reached: bool
    duration_ms: int


# ============================================================================
# Evaluation Schema
# ============================================================================

class EvaluationResult(BaseModel):
    """Result from conversation goal evaluation."""
    simulation_id: str
    flow_version_id: str
    test_goal: str
    goal_achieved: bool
    reasoning: str
    conversation_history: List[ConversationMessage]
    duration_ms: int
