"""
Configuration management for Spotify AI Agent.
Uses environment variables with .env file support.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


@dataclass
class SpotifyConfig:
    client_id: str
    client_secret: str
    redirect_uri: str = "http://localhost:8888/callback"
    scope: str = (
        "user-read-playback-state "
        "user-modify-playback-state "
        "user-read-currently-playing "
        "user-read-recently-played "
        "user-library-read "
        "user-top-read "
        "playlist-read-private "
        "playlist-read-collaborative"
    )


@dataclass
class LLMConfig:
    provider: str  # "groq", "gemini", "rule_based"
    api_key: str | None = None
    model: str | None = None


@dataclass
class Config:
    spotify: SpotifyConfig
    llm: LLMConfig
    data_dir: Path
    debug: bool = False


def load_config() -> Config:
    """Load configuration from environment variables."""

    # Spotify config
    spotify = SpotifyConfig(
        client_id=os.getenv("SPOTIFY_CLIENT_ID", ""),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET", ""),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback"),
    )

    # LLM config - defaults to rule_based (free, no API needed)
    llm_provider = os.getenv("LLM_PROVIDER", "rule_based")
    llm = LLMConfig(
        provider=llm_provider,
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", _default_model(llm_provider)),
    )

    # Data directory for memory/notes
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        spotify=spotify,
        llm=llm,
        data_dir=data_dir,
        debug=os.getenv("DEBUG", "false").lower() == "true",
    )


def _default_model(provider: str) -> str:
    """Return default model for each provider."""
    defaults = {
        "groq": "llama-3.1-8b-instant",
        "gemini": "gemini-1.5-flash",
        "rule_based": "",
    }
    return defaults.get(provider, "")
