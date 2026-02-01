"""
YouTube Music integration layer.
Uses ytmusicapi for searching and library access.

Note: YouTube Music doesn't have a "connect" feature like Spotify.
Playback is handled by opening URLs in browser or generating playlists.
"""

import webbrowser
from dataclasses import dataclass
from pathlib import Path

from ytmusicapi import YTMusic

from tools.base import MusicClient, Platform, Track, PlaybackState


@dataclass
class YouTubeMusicConfig:
    """Configuration for YouTube Music."""
    auth_file: Path | None = None  # Path to oauth.json or browser.json
    auth_type: str = "oauth"  # "oauth" or "browser"


class YouTubeMusicClient(MusicClient):
    """
    Client for YouTube Music API interactions.

    Limitations compared to Spotify:
    - No direct playback control (opens in browser)
    - No audio features API
    - No "devices" concept
    - History is limited
    """

    platform = Platform.YOUTUBE_MUSIC

    def __init__(self, config: YouTubeMusicConfig):
        self.config = config

        if config.auth_file and config.auth_file.exists():
            self._ytm = YTMusic(str(config.auth_file))
        else:
            # Unauthenticated - limited functionality
            self._ytm = YTMusic()

        self._authenticated = config.auth_file is not None and config.auth_file.exists()
        self._current_queue: list[Track] = []
        self._queue_index: int = 0
        self._is_playing: bool = False

    @property
    def user_id(self) -> str:
        """Get current user's ID."""
        if not self._authenticated:
            return "anonymous"
        try:
            # YTMusic doesn't have a direct user ID method
            # We'll use account info or return a placeholder
            return "youtube_user"
        except Exception:
            return "unknown"

    def is_authenticated(self) -> bool:
        """Check if client is authenticated."""
        return self._authenticated

    # -------------------------------------------------------------------------
    # Playback Control
    # -------------------------------------------------------------------------

    def get_playback_state(self) -> PlaybackState | None:
        """
        Get current playback state.
        Note: YTMusic doesn't track playback state - we simulate it.
        """
        if not self._current_queue:
            return None

        if self._queue_index >= len(self._current_queue):
            return None

        return PlaybackState(
            is_playing=self._is_playing,
            track=self._current_queue[self._queue_index],
            device_name="Browser",
            progress_ms=0,  # We can't track this
            shuffle=False,
            repeat="off",
        )

    def play_tracks(self, track_uris: list[str], device_id: str | None = None) -> bool:
        """
        Play tracks by opening in browser.
        track_uris should be YouTube video IDs.
        """
        if not track_uris:
            return False

        # Build queue from URIs
        self._current_queue = []
        for uri in track_uris:
            # Try to get track info
            try:
                song = self._ytm.get_song(uri)
                if song:
                    self._current_queue.append(self._song_to_track(song))
            except Exception:
                # Create minimal track
                self._current_queue.append(Track(
                    id=uri,
                    name="Unknown",
                    artist="Unknown",
                    album="",
                    uri=uri,
                    duration_ms=0,
                ))

        self._queue_index = 0
        self._is_playing = True

        # Open first track in browser
        if track_uris:
            url = f"https://music.youtube.com/watch?v={track_uris[0]}"
            webbrowser.open(url)
            return True

        return False

    def play_track_in_browser(self, track: Track) -> bool:
        """Open a specific track in the browser."""
        url = f"https://music.youtube.com/watch?v={track.id}"
        webbrowser.open(url)
        self._is_playing = True
        return True

    def pause(self) -> bool:
        """
        Pause playback.
        Note: Can't actually pause browser - just updates internal state.
        """
        self._is_playing = False
        return True

    def resume(self) -> bool:
        """Resume playback by reopening current track."""
        if self._current_queue and self._queue_index < len(self._current_queue):
            track = self._current_queue[self._queue_index]
            return self.play_track_in_browser(track)
        return False

    def next_track(self) -> bool:
        """Play next track in queue."""
        if self._queue_index + 1 < len(self._current_queue):
            self._queue_index += 1
            track = self._current_queue[self._queue_index]
            return self.play_track_in_browser(track)
        return False

    def previous_track(self) -> bool:
        """Play previous track in queue."""
        if self._queue_index > 0:
            self._queue_index -= 1
            track = self._current_queue[self._queue_index]
            return self.play_track_in_browser(track)
        return False

    def supports_playback_control(self) -> bool:
        """YouTube Music has limited playback control."""
        return False  # Opens in browser, no direct control

    def get_web_url(self, track: Track) -> str:
        """Get YouTube Music URL for a track."""
        return f"https://music.youtube.com/watch?v={track.id}"

    # -------------------------------------------------------------------------
    # Library & Tracks
    # -------------------------------------------------------------------------

    def get_liked_songs(self, limit: int = 50) -> list[Track]:
        """Get user's liked songs."""
        if not self._authenticated:
            return []

        try:
            playlist = self._ytm.get_liked_songs(limit=limit)
            if not playlist or "tracks" not in playlist:
                return []
            return [self._playlist_item_to_track(t) for t in playlist["tracks"][:limit] if t]
        except Exception:
            return []

    def get_recently_played(self, limit: int = 50) -> list[Track]:
        """Get recently played tracks (history)."""
        if not self._authenticated:
            return []

        try:
            history = self._ytm.get_history()
            tracks = []
            for item in history[:limit]:
                if item.get("videoId"):
                    tracks.append(self._history_item_to_track(item))
            return tracks
        except Exception:
            return []

    def search_tracks(self, query: str, limit: int = 20) -> list[Track]:
        """Search for tracks."""
        try:
            results = self._ytm.search(query, filter="songs", limit=limit)
            return [self._search_result_to_track(r) for r in results if r.get("videoId")]
        except Exception:
            return []

    def get_top_tracks(self, time_range: str = "medium_term", limit: int = 50) -> list[Track]:
        """
        Get user's top tracks.
        YTMusic doesn't have this - return liked songs as proxy.
        """
        return self.get_liked_songs(limit=limit)

    def get_recommendations(
        self,
        seed_tracks: list[str] | None = None,
        seed_artists: list[str] | None = None,
        seed_genres: list[str] | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[Track]:
        """Get recommendations based on a track."""
        if not seed_tracks:
            return []

        try:
            # Get watch playlist (recommendations based on a song)
            watch = self._ytm.get_watch_playlist(videoId=seed_tracks[0], limit=limit)
            if not watch or "tracks" not in watch:
                return []
            return [self._playlist_item_to_track(t) for t in watch["tracks"][:limit] if t]
        except Exception:
            return []

    # -------------------------------------------------------------------------
    # Playlists
    # -------------------------------------------------------------------------

    def get_playlists(self, limit: int = 20) -> list[dict]:
        """Get user's playlists."""
        if not self._authenticated:
            return []

        try:
            playlists = self._ytm.get_library_playlists(limit=limit)
            return [
                {
                    "id": p.get("playlistId", ""),
                    "name": p.get("title", "Unknown"),
                    "count": p.get("count", 0),
                }
                for p in playlists
            ]
        except Exception:
            return []

    def get_playlist_tracks(self, playlist_id: str, limit: int = 50) -> list[Track]:
        """Get tracks from a playlist."""
        try:
            playlist = self._ytm.get_playlist(playlist_id, limit=limit)
            if not playlist or "tracks" not in playlist:
                return []
            return [self._playlist_item_to_track(t) for t in playlist["tracks"][:limit] if t]
        except Exception:
            return []

    # -------------------------------------------------------------------------
    # Conversion helpers
    # -------------------------------------------------------------------------

    def _search_result_to_track(self, result: dict) -> Track:
        """Convert search result to Track."""
        artists = result.get("artists", [])
        artist_names = ", ".join(a.get("name", "") for a in artists) if artists else "Unknown"

        album = result.get("album", {})
        album_name = album.get("name", "") if album else ""

        duration = result.get("duration_seconds", 0) * 1000 if result.get("duration_seconds") else 0

        return Track(
            id=result.get("videoId", ""),
            name=result.get("title", "Unknown"),
            artist=artist_names,
            album=album_name,
            uri=result.get("videoId", ""),
            duration_ms=duration,
            popularity=50,  # YTMusic doesn't provide this
        )

    def _playlist_item_to_track(self, item: dict) -> Track:
        """Convert playlist item to Track."""
        if not item:
            return Track(id="", name="Unknown", artist="Unknown", album="", uri="", duration_ms=0)

        artists = item.get("artists", [])
        artist_names = ", ".join(a.get("name", "") for a in artists) if artists else "Unknown"

        album = item.get("album", {})
        album_name = album.get("name", "") if album else ""

        duration = item.get("duration_seconds", 0) * 1000 if item.get("duration_seconds") else 0

        video_id = item.get("videoId", "")

        return Track(
            id=video_id,
            name=item.get("title", "Unknown"),
            artist=artist_names,
            album=album_name,
            uri=video_id,
            duration_ms=duration,
            popularity=50,
        )

    def _history_item_to_track(self, item: dict) -> Track:
        """Convert history item to Track."""
        return self._playlist_item_to_track(item)

    def _song_to_track(self, song: dict) -> Track:
        """Convert song details to Track."""
        video_details = song.get("videoDetails", {})

        return Track(
            id=video_details.get("videoId", ""),
            name=video_details.get("title", "Unknown"),
            artist=video_details.get("author", "Unknown"),
            album="",
            uri=video_details.get("videoId", ""),
            duration_ms=int(video_details.get("lengthSeconds", 0)) * 1000,
            popularity=50,
        )


def setup_youtube_auth(auth_file: Path) -> bool:
    """
    Interactive setup for YouTube Music authentication.
    Returns True if setup was successful.
    """
    from rich.console import Console
    from rich.panel import Panel

    console = Console()

    console.print(Panel(
        "[bold cyan]YouTube Music Authentication Setup[/bold cyan]\n\n"
        "Choose authentication method:\n"
        "  [1] OAuth (Recommended) - Opens browser for Google login\n"
        "  [2] Browser headers - Copy from browser dev tools\n\n"
        "OAuth is easier but may require re-auth periodically.",
        border_style="cyan",
    ))

    choice = input("\nEnter choice (1 or 2): ").strip()

    try:
        if choice == "1":
            console.print("\n[dim]Opening browser for Google login...[/dim]")
            YTMusic.setup(filepath=str(auth_file), open_browser=True)
            console.print(f"[green]Authentication saved to {auth_file}[/green]")
            return True
        elif choice == "2":
            console.print("\n[yellow]Browser header authentication:[/yellow]")
            console.print("1. Open YouTube Music in your browser")
            console.print("2. Open Developer Tools (F12)")
            console.print("3. Go to Network tab")
            console.print("4. Click on any request to music.youtube.com")
            console.print("5. Copy the 'cookie' header value")
            console.print("\nPaste the headers when prompted by ytmusicapi.\n")
            YTMusic.setup(filepath=str(auth_file))
            console.print(f"[green]Authentication saved to {auth_file}[/green]")
            return True
        else:
            console.print("[red]Invalid choice[/red]")
            return False
    except Exception as e:
        console.print(f"[red]Setup failed: {e}[/red]")
        return False
