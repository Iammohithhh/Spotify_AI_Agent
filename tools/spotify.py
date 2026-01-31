"""
Spotify integration layer.
Handles authentication, playback control, and track fetching.
"""

from dataclasses import dataclass
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from config import SpotifyConfig


@dataclass
class Track:
    id: str
    name: str
    artist: str
    album: str
    uri: str
    duration_ms: int
    popularity: int

    @classmethod
    def from_spotify(cls, data: dict) -> "Track":
        """Create Track from Spotify API response."""
        artists = ", ".join(a["name"] for a in data.get("artists", []))
        return cls(
            id=data["id"],
            name=data["name"],
            artist=artists,
            album=data.get("album", {}).get("name", ""),
            uri=data["uri"],
            duration_ms=data.get("duration_ms", 0),
            popularity=data.get("popularity", 0),
        )

    def __str__(self) -> str:
        return f"{self.name} - {self.artist}"


@dataclass
class PlaybackState:
    is_playing: bool
    track: Track | None
    device_name: str | None
    progress_ms: int
    shuffle: bool
    repeat: str  # "off", "track", "context"


@dataclass
class AudioFeatures:
    """Spotify audio features for a track."""
    track_id: str
    energy: float       # 0.0 - 1.0
    valence: float      # 0.0 - 1.0 (musical positiveness)
    danceability: float
    tempo: float        # BPM
    acousticness: float
    instrumentalness: float

    @property
    def mood_label(self) -> str:
        """Derive a simple mood from audio features."""
        if self.valence < 0.3 and self.energy < 0.4:
            return "sad"
        elif self.valence > 0.6 and self.energy > 0.6:
            return "happy"
        elif self.energy > 0.7:
            return "energetic"
        elif self.energy < 0.3:
            return "calm"
        else:
            return "neutral"


class SpotifyClient:
    """Client for Spotify API interactions."""

    def __init__(self, config: SpotifyConfig, cache_path: Path | None = None):
        self.config = config
        cache_file = str(cache_path) if cache_path else ".spotify_cache"

        self._sp = spotipy.Spotify(
            auth_manager=SpotifyOAuth(
                client_id=config.client_id,
                client_secret=config.client_secret,
                redirect_uri=config.redirect_uri,
                scope=config.scope,
                cache_path=cache_file,
                open_browser=True,
            )
        )
        self._user_id: str | None = None

    @property
    def user_id(self) -> str:
        """Get current user's Spotify ID."""
        if not self._user_id:
            self._user_id = self._sp.current_user()["id"]
        return self._user_id

    # -------------------------------------------------------------------------
    # Playback Control
    # -------------------------------------------------------------------------

    def get_playback_state(self) -> PlaybackState | None:
        """Get current playback state."""
        state = self._sp.current_playback()
        if not state:
            return None

        track = None
        if state.get("item"):
            track = Track.from_spotify(state["item"])

        device = state.get("device", {})
        return PlaybackState(
            is_playing=state.get("is_playing", False),
            track=track,
            device_name=device.get("name"),
            progress_ms=state.get("progress_ms", 0),
            shuffle=state.get("shuffle_state", False),
            repeat=state.get("repeat_state", "off"),
        )

    def get_devices(self) -> list[dict]:
        """Get available Spotify devices."""
        result = self._sp.devices()
        return result.get("devices", [])

    def play_tracks(self, track_uris: list[str], device_id: str | None = None) -> bool:
        """
        Start playback with given tracks.
        Returns True if successful, False otherwise.
        """
        try:
            # If no device specified, try to find an active one
            if not device_id:
                devices = self.get_devices()
                if not devices:
                    return False
                # Prefer active device, otherwise use first available
                active = next((d for d in devices if d["is_active"]), None)
                device_id = (active or devices[0])["id"]

            self._sp.start_playback(device_id=device_id, uris=track_uris)
            return True
        except spotipy.SpotifyException:
            return False

    def pause(self) -> bool:
        """Pause playback."""
        try:
            self._sp.pause_playback()
            return True
        except spotipy.SpotifyException:
            return False

    def resume(self) -> bool:
        """Resume playback."""
        try:
            self._sp.start_playback()
            return True
        except spotipy.SpotifyException:
            return False

    def next_track(self) -> bool:
        """Skip to next track."""
        try:
            self._sp.next_track()
            return True
        except spotipy.SpotifyException:
            return False

    def previous_track(self) -> bool:
        """Go to previous track."""
        try:
            self._sp.previous_track()
            return True
        except spotipy.SpotifyException:
            return False

    def set_shuffle(self, state: bool) -> bool:
        """Set shuffle mode."""
        try:
            self._sp.shuffle(state)
            return True
        except spotipy.SpotifyException:
            return False

    def queue_track(self, track_uri: str) -> bool:
        """Add track to queue."""
        try:
            self._sp.add_to_queue(track_uri)
            return True
        except spotipy.SpotifyException:
            return False

    # -------------------------------------------------------------------------
    # Library & Tracks
    # -------------------------------------------------------------------------

    def get_liked_songs(self, limit: int = 50) -> list[Track]:
        """Get user's liked songs."""
        tracks = []
        results = self._sp.current_user_saved_tracks(limit=min(limit, 50))

        while results and len(tracks) < limit:
            for item in results["items"]:
                tracks.append(Track.from_spotify(item["track"]))
                if len(tracks) >= limit:
                    break

            if results["next"] and len(tracks) < limit:
                results = self._sp.next(results)
            else:
                break

        return tracks

    def get_recently_played(self, limit: int = 50) -> list[Track]:
        """Get recently played tracks."""
        results = self._sp.current_user_recently_played(limit=min(limit, 50))
        return [Track.from_spotify(item["track"]) for item in results["items"]]

    def get_top_tracks(self, time_range: str = "medium_term", limit: int = 50) -> list[Track]:
        """
        Get user's top tracks.
        time_range: short_term (4 weeks), medium_term (6 months), long_term (years)
        """
        results = self._sp.current_user_top_tracks(
            limit=min(limit, 50),
            time_range=time_range,
        )
        return [Track.from_spotify(item) for item in results["items"]]

    def search_tracks(self, query: str, limit: int = 20) -> list[Track]:
        """Search for tracks."""
        results = self._sp.search(q=query, type="track", limit=limit)
        return [Track.from_spotify(item) for item in results["tracks"]["items"]]

    def get_audio_features(self, track_ids: list[str]) -> list[AudioFeatures]:
        """Get audio features for tracks."""
        features = []
        # API allows max 100 at a time
        for i in range(0, len(track_ids), 100):
            batch = track_ids[i:i + 100]
            results = self._sp.audio_features(batch)
            for f in results:
                if f:  # Can be None for some tracks
                    features.append(AudioFeatures(
                        track_id=f["id"],
                        energy=f["energy"],
                        valence=f["valence"],
                        danceability=f["danceability"],
                        tempo=f["tempo"],
                        acousticness=f["acousticness"],
                        instrumentalness=f["instrumentalness"],
                    ))
        return features

    def get_recommendations(
        self,
        seed_tracks: list[str] | None = None,
        seed_artists: list[str] | None = None,
        seed_genres: list[str] | None = None,
        limit: int = 20,
        **kwargs,  # target_energy, target_valence, etc.
    ) -> list[Track]:
        """
        Get track recommendations based on seeds.
        At least one seed required. Max 5 seeds total.
        """
        results = self._sp.recommendations(
            seed_tracks=seed_tracks,
            seed_artists=seed_artists,
            seed_genres=seed_genres,
            limit=limit,
            **kwargs,
        )
        return [Track.from_spotify(item) for item in results["tracks"]]

    # -------------------------------------------------------------------------
    # Podcasts
    # -------------------------------------------------------------------------

    def get_current_episode(self) -> dict | None:
        """Get currently playing podcast episode."""
        state = self._sp.current_playback(additional_types="episode")
        if not state or state.get("currently_playing_type") != "episode":
            return None

        item = state.get("item", {})
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "show": item.get("show", {}).get("name"),
            "description": item.get("description", ""),
            "duration_ms": item.get("duration_ms", 0),
            "progress_ms": state.get("progress_ms", 0),
        }

    def get_saved_shows(self, limit: int = 20) -> list[dict]:
        """Get user's saved podcast shows."""
        results = self._sp.current_user_saved_shows(limit=limit)
        shows = []
        for item in results["items"]:
            show = item["show"]
            shows.append({
                "id": show["id"],
                "name": show["name"],
                "publisher": show["publisher"],
                "description": show.get("description", ""),
            })
        return shows
