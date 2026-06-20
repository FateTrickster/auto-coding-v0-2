"""Configuration from environment and .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _find_dotenv() -> Path | None:
    """Walk up from cwd to find .env."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        env_file = parent / ".env"
        if env_file.exists():
            return env_file
    return None


def load_config(env_path: str | Path | None = None) -> "Config":
    """Load configuration, optionally from a specific .env path."""
    if env_path is None:
        env_path = _find_dotenv()
    if env_path:
        load_dotenv(env_path, override=True)

    return Config(
        api_key=os.getenv("LLM_API_KEY", ""),
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        model_coder_a=os.getenv("LLM_MODEL_CODER_A", "gpt-4o"),
        model_coder_b=os.getenv("LLM_MODEL_CODER_B", "gpt-4o"),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1600")),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
    )


@dataclass
class Config:
    api_key: str
    base_url: str
    model_coder_a: str
    model_coder_b: str
    max_tokens: int = 1600
    temperature: float = 0.0

    # Coding parameters
    request_timeout: float = 120.0
    max_retries: int = 3

    # Labels
    valid_labels: tuple[str, ...] = ("IS1", "IS2", "IS3", "IS4")
