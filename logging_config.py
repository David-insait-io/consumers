"""Centralized logging configuration."""

import logging
import sys
from datetime import datetime
from typing import Optional
from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)

        # Add timestamp
        log_record['timestamp'] = datetime.utcnow().isoformat() + 'Z'

        # Add level
        log_record['level'] = record.levelname

        # Add logger name
        log_record['logger'] = record.name

        # Add source location
        log_record['source'] = f"{record.filename}:{record.lineno}"

        # Remove redundant fields
        if 'message' not in log_record and 'msg' in log_record:
            log_record['message'] = log_record.pop('msg')


def setup_logging(level: str = "INFO", json_format: bool = True):
    """
    Setup centralized logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_format: If True, output JSON logs (for production)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))

    if json_format:
        # JSON format for production (easier to parse by log aggregators)
        formatter = CustomJsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s'
        )
    else:
        # Human-readable format for development
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    return root_logger


class ConversationLogger:
    """Logger for conversation events with structured data."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("conversation")

    def conversation_started(self, simulation_id: str, persona_name: str, test_goal: str):
        """Log conversation start."""
        self.logger.info(
            "Conversation started",
            extra={
                "event": "conversation_started",
                "simulation_id": simulation_id,
                "persona_name": persona_name,
                "test_goal": test_goal
            }
        )

    def conversation_completed(
        self,
        simulation_id: str,
        iterations: int,
        duration_ms: int,
        end_reason: str,
        goal_reached: bool
    ):
        """Log conversation completion."""
        self.logger.info(
            "Conversation completed",
            extra={
                "event": "conversation_completed",
                "simulation_id": simulation_id,
                "iterations": iterations,
                "duration_ms": duration_ms,
                "end_reason": end_reason,
                "goal_reached": goal_reached
            }
        )

    def conversation_failed(self, simulation_id: str, error: str, iteration: int = 0):
        """Log conversation failure."""
        self.logger.error(
            "Conversation failed",
            extra={
                "event": "conversation_failed",
                "simulation_id": simulation_id,
                "error": error,
                "iteration": iteration
            }
        )

    def chatbot_request(self, simulation_id: str, iteration: int, message_preview: str):
        """Log chatbot API request."""
        self.logger.debug(
            "Chatbot request",
            extra={
                "event": "chatbot_request",
                "simulation_id": simulation_id,
                "iteration": iteration,
                "message_preview": message_preview[:100]
            }
        )

    def chatbot_response(self, simulation_id: str, iteration: int, latency_ms: int, response_preview: str):
        """Log chatbot API response."""
        self.logger.debug(
            "Chatbot response",
            extra={
                "event": "chatbot_response",
                "simulation_id": simulation_id,
                "iteration": iteration,
                "latency_ms": latency_ms,
                "response_preview": response_preview[:100]
            }
        )

    def llm_request(self, simulation_id: str, model: str, purpose: str):
        """Log LLM API request."""
        self.logger.debug(
            "LLM request",
            extra={
                "event": "llm_request",
                "simulation_id": simulation_id,
                "model": model,
                "purpose": purpose
            }
        )

    def llm_response(self, simulation_id: str, latency_ms: int):
        """Log LLM API response."""
        self.logger.debug(
            "LLM response",
            extra={
                "event": "llm_response",
                "simulation_id": simulation_id,
                "latency_ms": latency_ms
            }
        )

    def llm_error(self, simulation_id: str, error: str, attempt: int):
        """Log LLM API error."""
        self.logger.warning(
            "LLM error",
            extra={
                "event": "llm_error",
                "simulation_id": simulation_id,
                "error": error,
                "attempt": attempt
            }
        )

    def result_saved(self, simulation_id: str, file_path: str):
        """Log result saved to file."""
        self.logger.info(
            "Result saved",
            extra={
                "event": "result_saved",
                "simulation_id": simulation_id,
                "file_path": file_path
            }
        )

    def progress(self, completed: int, failed: int, rate: float, eta_seconds: Optional[float] = None):
        """Log batch progress."""
        self.logger.info(
            "Progress update",
            extra={
                "event": "progress",
                "completed": completed,
                "failed": failed,
                "rate_per_second": round(rate, 2),
                "eta_seconds": round(eta_seconds, 0) if eta_seconds else None
            }
        )
