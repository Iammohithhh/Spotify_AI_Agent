"""Tools for the Music AI Agent."""

from tools.base import MusicClient, Track, PlaybackState, Platform
from tools.spotify import SpotifyClient
from tools.youtube_music import YouTubeMusicClient
from tools.notes import NotesManager, PodcastNote

__all__ = [
    "MusicClient",
    "Track",
    "PlaybackState",
    "Platform",
    "SpotifyClient",
    "YouTubeMusicClient",
    "NotesManager",
    "PodcastNote",
]
