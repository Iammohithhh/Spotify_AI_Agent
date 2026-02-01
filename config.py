"""
Configuration management for Music AI Agent.
Uses environment variables with .env file support.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


class Platform(Enum):
    SPOTIFY = "spotify"
    YOUTUBE_MUSIC = "youtube_music"


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
class YouTubeMusicConfig:
    auth_file: Path | None = None
    auth_type: str = "oauth"  # "oauth" or "browser"


@dataclass
class LLMConfig:
    provider: str  # "groq", "gemini", "rule_based"
    api_key: str | None = None
    model: str | None = None


@dataclass
class Config:
    platform: Platform
    spotify: SpotifyConfig
    youtube_music: YouTubeMusicConfig
    llm: LLMConfig
    data_dir: Path
    debug: bool = False


def load_config() -> Config:
    """Load configuration from environment variables."""

    # Platform selection - defaults to youtube_music (no API key needed)
    platform_str = os.getenv("MUSIC_PLATFORM", "youtube_music").lower()
    platform = Platform.YOUTUBE_MUSIC
    if platform_str == "spotify":
        platform = Platform.SPOTIFY

    # Data directory for memory/notes
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    # Spotify config
    spotify = SpotifyConfig(
        client_id=os.getenv("SPOTIFY_CLIENT_ID", ""),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET", ""),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback"),
    )

    # YouTube Music config
    yt_auth_file = os.getenv("YTMUSIC_AUTH_FILE", "")
    youtube_music = YouTubeMusicConfig(
        auth_file=Path(yt_auth_file) if yt_auth_file else data_dir / "ytmusic_auth.json",
        auth_type=os.getenv("YTMUSIC_AUTH_TYPE", "oauth"),
    )

    # LLM config - defaults to rule_based (free, no API needed)
    llm_provider = os.getenv("LLM_PROVIDER", "rule_based")
    llm = LLMConfig(
        provider=llm_provider,
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", _default_model(llm_provider)),
    )

    return Config(
        platform=platform,
        spotify=spotify,
        youtube_music=youtube_music,
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
