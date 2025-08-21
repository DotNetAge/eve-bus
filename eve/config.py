"""Eve Bus configuration

This module contains configuration settings for the Eve Bus.
"""
import os
from typing import Optional

# Event channel prefix for Redis
EVENT_CHANNEL: str = os.getenv("EVENT_CHANNEL", "event")

# Redis configuration (can be overridden by environment variables)
REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")