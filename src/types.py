"""
Shared type definitions for the Grok bot.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ToolCall:
    """Represents an AI tool call request."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AIResponse:
    """Standardized response from AI service."""
    content: str
    tool_calls: list[ToolCall] | None = None


@dataclass
class ChatMessage:
    """Platform-agnostic chat message."""
    id: int
    role: str  # "user" | "assistant" | "system"
    content: str
    author_id: int | None = None
    timestamp: datetime | None = None


@dataclass
class MessageContent:
    """Multimodal message content for AI."""
    type: str  # "text" | "image_url"
    text: str | None = None
    image_url: dict[str, str] | None = None


@dataclass
class UserDigestSettings:
    """User's digest configuration."""
    user_id: int
    guild_id: int
    timezone: str = "UTC"
    daily_time: str = "09:00"
    last_sent_at: datetime | None = None


@dataclass
class DigestTopic:
    """A single digest topic."""
    id: int
    user_id: int
    guild_id: int
    topic: str
    created_at: datetime | None = None


@dataclass
class Persona:
    """Bot persona configuration."""
    id: int
    name: str
    description: str
    system_prompt: str
    is_global: bool = False
    created_by: int | None = None


@dataclass
class ChannelSummary:
    """Conversation summary for a channel."""
    channel_id: int
    content: str
    last_msg_id: int
    updated_at: datetime | None = None
