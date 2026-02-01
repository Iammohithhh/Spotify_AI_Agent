"""
Base classes for music platform clients.
Defines the interface that all platform clients must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class Platform(Enum):
    SPOTIFY = "spotify"
    YOUTUBE_MUSIC = "youtube_music"


@dataclass
class Track:
    """Platform-agnostic track representation."""
    id: str
    name: str
    artist: str
    album: str
    uri: str  # Platform-specific URI/URL
    duration_ms: int
    popularity: int = 50  # Default for platforms without this

    def __str__(self) -> str:
        return f"{self.name} - {self.artist}"


@dataclass
class PlaybackState:
    """Current playback state."""
    is_playing: bool
    track: Track | None
    device_name: str | None
    progress_ms: int
    shuffle: bool = False
    repeat: str = "off"


class MusicClient(ABC):
    """Abstract base class for music platform clients."""

    platform: Platform

    @property
    @abstractmethod
    def user_id(self) -> str:
        """Get current user's ID."""
        pass

    # -------------------------------------------------------------------------
    # Playback Control
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_playback_state(self) -> PlaybackState | None:
        """Get current playback state."""
        pass

    @abstractmethod
    def play_tracks(self, track_uris: list[str], device_id: str | None = None) -> bool:
        """Start playback with given tracks."""
        pass

    @abstractmethod
    def pause(self) -> bool:
        """Pause playback."""
        pass

    @abstractmethod
    def resume(self) -> bool:
        """Resume playback."""
        pass

    @abstractmethod
    def next_track(self) -> bool:
        """Skip to next track."""
        pass

    @abstractmethod
    def previous_track(self) -> bool:
        """Go to previous track."""
        pass

    def set_shuffle(self, state: bool) -> bool:
        """Set shuffle mode. Optional - not all platforms support this."""
        return False

    def queue_track(self, track_uri: str) -> bool:
        """Add track to queue. Optional."""
        return False

    def get_devices(self) -> list[dict]:
        """Get available devices. Optional."""
        return []

    # -------------------------------------------------------------------------
    # Library & Tracks
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_liked_songs(self, limit: int = 50) -> list[Track]:
        """Get user's liked songs."""
        pass

    @abstractmethod
    def get_recently_played(self, limit: int = 50) -> list[Track]:
        """Get recently played tracks."""
        pass

    @abstractmethod
    def search_tracks(self, query: str, limit: int = 20) -> list[Track]:
        """Search for tracks."""
        pass

    def get_top_tracks(self, time_range: str = "medium_term", limit: int = 50) -> list[Track]:
        """Get user's top tracks. Optional."""
        return []

    def get_audio_features(self, track_ids: list[str]) -> list[dict]:
        """Get audio features for tracks. Optional - Spotify only."""
        return []

    def get_recommendations(
        self,
        seed_tracks: list[str] | None = None,
        seed_artists: list[str] | None = None,
        seed_genres: list[str] | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[Track]:
        """Get track recommendations. Optional."""
        return []

    # -------------------------------------------------------------------------
    # Podcasts (Optional)
    # -------------------------------------------------------------------------

    def get_current_episode(self) -> dict | None:
        """Get currently playing podcast episode."""
        return None

    def get_saved_shows(self, limit: int = 20) -> list[dict]:
        """Get user's saved podcast shows."""
        return []

    # -------------------------------------------------------------------------
    # Platform-specific helpers
    # -------------------------------------------------------------------------

    def supports_playback_control(self) -> bool:
        """Whether this platform supports direct playback control."""
        return True

    def get_web_url(self, track: Track) -> str | None:
        """Get web URL for a track (for opening in browser)."""
        return None
