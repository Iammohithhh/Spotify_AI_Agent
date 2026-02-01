"""
Agent Orchestrator - The core brain of the system.
Coordinates intent parsing, memory, and music platform actions.
Works with both Spotify and YouTube Music.
"""

from dataclasses import dataclass

from agent.intent_parser import Intent, IntentParser, ContentType, ControlAction, Mood
from agent.memory import Memory
from tools.base import MusicClient, Track, Platform
from config import Config


@dataclass
class AgentResponse:
    """Response from the agent."""
    message: str
    tracks_played: list[Track] | None = None
    action_taken: str | None = None
    success: bool = True
    open_url: str | None = None  # For browser-based playback


class Agent:
    """
    The main agent that orchestrates all components.
    This is the single entry point for user interactions.
    Works with any MusicClient implementation.
    """

    def __init__(self, config: Config, music_client: MusicClient):
        self.config = config
        self.client = music_client
        self.parser = IntentParser()
        self.memory = Memory(config.data_dir / "memory.json")

        # Cache for audio features (Spotify only)
        self._features_cache: dict[str, dict] = {}

    @property
    def platform_name(self) -> str:
        """Get human-readable platform name."""
        return "YouTube Music" if self.client.platform == Platform.YOUTUBE_MUSIC else "Spotify"

    def run(self, user_input: str) -> AgentResponse:
        """
        Main entry point. Process user input and return response.
        """
        # Step 1: Parse intent
        intent = self.parser.parse(user_input)

        # Step 2: Route to appropriate handler
        if intent.content_type == ContentType.CONTROL:
            return self._handle_control(intent)
        elif intent.content_type == ContentType.QUERY:
            return self._handle_query(intent)
        elif intent.content_type == ContentType.PODCAST:
            return self._handle_podcast(intent)
        elif intent.content_type == ContentType.MUSIC:
            return self._handle_music(intent)
        else:
            return AgentResponse(
                message="I'm not sure what you want. Try asking for music by mood, language, or artist.",
                success=False,
            )

    def _handle_control(self, intent: Intent) -> AgentResponse:
        """Handle playback control commands."""
        action = intent.control_action
        platform = self.platform_name

        if action == ControlAction.PAUSE:
            success = self.client.pause()
            msg = "Paused." if success else f"Couldn't pause. Is {platform} open?"
            return AgentResponse(message=msg, action_taken="pause", success=success)

        elif action == ControlAction.RESUME:
            success = self.client.resume()
            msg = "Resuming." if success else f"Couldn't resume. Is {platform} open?"
            return AgentResponse(message=msg, action_taken="resume", success=success)

        elif action == ControlAction.NEXT:
            success = self.client.next_track()
            msg = "Skipped." if success else "No next track in queue."
            return AgentResponse(message=msg, action_taken="next", success=success)

        elif action == ControlAction.PREVIOUS:
            success = self.client.previous_track()
            msg = "Going back." if success else "No previous track."
            return AgentResponse(message=msg, action_taken="previous", success=success)

        elif action == ControlAction.SHUFFLE:
            success = self.client.set_shuffle(True)
            if success:
                return AgentResponse(message="Shuffle on.", action_taken="shuffle", success=True)
            else:
                return AgentResponse(
                    message=f"Shuffle not supported on {platform}.",
                    success=False,
                )

        return AgentResponse(message="Unknown control command.", success=False)

    def _handle_query(self, intent: Intent) -> AgentResponse:
        """Handle queries about current playback."""
        state = self.client.get_playback_state()

        if not state or not state.track:
            return AgentResponse(
                message="Nothing is playing right now.",
                action_taken="query",
            )

        track = state.track
        status = "Playing" if state.is_playing else "Paused"
        device = f" on {state.device_name}" if state.device_name else ""

        return AgentResponse(
            message=f"{status}: {track.name} by {track.artist}{device}",
            action_taken="query",
        )

    def _handle_podcast(self, intent: Intent) -> AgentResponse:
        """Handle podcast-related requests."""
        episode = self.client.get_current_episode()

        if episode:
            progress_pct = int((episode["progress_ms"] / episode["duration_ms"]) * 100)
            return AgentResponse(
                message=f"Listening to: {episode['name']} ({episode['show']})\nProgress: {progress_pct}%",
                action_taken="podcast_query",
            )

        # Show saved podcasts
        shows = self.client.get_saved_shows(limit=5)
        if shows:
            show_list = "\n".join(f"  - {s['name']}" for s in shows)
            return AgentResponse(
                message=f"Your saved podcasts:\n{show_list}",
                action_taken="podcast_list",
            )

        return AgentResponse(
            message=f"Podcasts not available or none saved on {self.platform_name}.",
            success=False,
        )

    def _handle_music(self, intent: Intent) -> AgentResponse:
        """Handle music requests - the main feature."""

        # Step 1: Gather candidate tracks
        candidates = self._gather_candidates(intent)

        if not candidates:
            return AgentResponse(
                message=f"Couldn't find matching tracks on {self.platform_name}. Try different keywords.",
                success=False,
            )

        # Step 2: Filter and rank based on intent
        ranked_tracks = self._rank_tracks(candidates, intent)

        if not ranked_tracks:
            ranked_tracks = candidates[:20]  # Fallback to unranked

        # Step 3: Play tracks
        track_uris = [t.uri for t in ranked_tracks[:20]]
        success = self.client.play_tracks(track_uris)

        # For YouTube Music, playback opens in browser
        open_url = None
        if self.client.platform == Platform.YOUTUBE_MUSIC and ranked_tracks:
            open_url = self.client.get_web_url(ranked_tracks[0])

        if not success and self.client.platform == Platform.SPOTIFY:
            devices = self.client.get_devices()
            if not devices:
                return AgentResponse(
                    message="No Spotify device found. Open Spotify on any device and try again.",
                    success=False,
                )
            return AgentResponse(
                message="Couldn't start playback. Make sure Spotify is open.",
                success=False,
            )

        # Step 4: Record to memory
        mood_str = intent.mood.value if intent.mood else "neutral"
        for track in ranked_tracks[:5]:
            self.memory.record(
                track_id=track.id,
                track_name=track.name,
                artist=track.artist,
                action="played",
                mood=mood_str,
                language=intent.language,
                energy=intent.energy_level,
            )

        # Step 5: Build response
        first_track = ranked_tracks[0]
        count = len(ranked_tracks)
        mood_desc = f" {intent.mood.value}" if intent.mood != Mood.NEUTRAL else ""
        lang_desc = f" {intent.language}" if intent.language else ""

        msg = f"Playing{mood_desc}{lang_desc}: {first_track.name} by {first_track.artist}"
        if count > 1:
            msg += f" (+{count - 1} more)"

        if self.client.platform == Platform.YOUTUBE_MUSIC:
            msg += "\n[Opening in browser]"

        return AgentResponse(
            message=msg,
            tracks_played=ranked_tracks[:10],
            action_taken="play_music",
            success=True,
            open_url=open_url,
        )

    def _gather_candidates(self, intent: Intent) -> list[Track]:
        """Gather candidate tracks based on intent."""
        candidates: list[Track] = []

        # If artist specified, search for artist
        if intent.artist:
            search_query = intent.artist
            if intent.language:
                search_query += f" {intent.language}"
            candidates.extend(self.client.search_tracks(search_query, limit=30))

        # If high familiarity requested, prioritize liked songs
        if intent.familiarity == "high":
            liked = self.client.get_liked_songs(limit=100)
            candidates.extend(liked)

        # If language specified, search by language
        if intent.language:
            lang_query = f"{intent.language} songs"
            if intent.mood != Mood.NEUTRAL:
                lang_query = f"{intent.language} {intent.mood.value} songs"
            candidates.extend(self.client.search_tracks(lang_query, limit=30))

        # If we still don't have enough, use recently played and top tracks
        if len(candidates) < 20:
            candidates.extend(self.client.get_recently_played(limit=30))
            candidates.extend(self.client.get_top_tracks(limit=30))

        # If still nothing and we have a mood, search by mood
        if len(candidates) < 10 and intent.mood != Mood.NEUTRAL:
            mood_query = f"{intent.mood.value} music"
            candidates.extend(self.client.search_tracks(mood_query, limit=20))

        # Last resort: just search for popular music
        if len(candidates) < 5:
            candidates.extend(self.client.search_tracks("popular hits", limit=20))

        # Deduplicate by track ID
        seen = set()
        unique = []
        for track in candidates:
            if track.id and track.id not in seen:
                seen.add(track.id)
                unique.append(track)

        return unique

    def _rank_tracks(self, tracks: list[Track], intent: Intent) -> list[Track]:
        """Rank tracks based on how well they match the intent."""
        if not tracks:
            return []

        # Get tracks that performed well for this mood from memory
        good_track_ids = set()
        if intent.mood != Mood.NEUTRAL:
            good_track_ids = set(self.memory.get_tracks_for_mood(intent.mood.value, limit=50))

        # Try to get audio features (Spotify only)
        features_map = {}
        if self.client.platform == Platform.SPOTIFY:
            track_ids = [t.id for t in tracks]
            features_list = self._get_features(track_ids)
            features_map = {f["track_id"]: f for f in features_list}

        # Score each track
        scored: list[tuple[Track, float]] = []

        for track in tracks:
            score = 0.0

            # Boost if track was good for this mood before
            if track.id in good_track_ids:
                score += 3.0

            # Match energy level (if we have audio features)
            features = features_map.get(track.id)
            if features:
                energy_diff = abs(features.get("energy", 0.5) - intent.energy_level)
                score += (1 - energy_diff) * 2

                # Match valence for happy/sad moods
                valence = features.get("valence", 0.5)
                energy = features.get("energy", 0.5)

                if intent.mood == Mood.SAD and valence < 0.4:
                    score += 1.5
                elif intent.mood == Mood.HAPPY and valence > 0.6:
                    score += 1.5
                elif intent.mood == Mood.CALM and energy < 0.4:
                    score += 1.5
                elif intent.mood == Mood.ENERGETIC and energy > 0.7:
                    score += 1.5

            # Popularity as tiebreaker
            score += track.popularity / 200

            scored.append((track, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        return [t for t, _ in scored]

    def _get_features(self, track_ids: list[str]) -> list[dict]:
        """Get audio features with caching (Spotify only)."""
        if self.client.platform != Platform.SPOTIFY:
            return []

        uncached = [tid for tid in track_ids if tid not in self._features_cache]

        if uncached:
            new_features = self.client.get_audio_features(uncached)
            for f in new_features:
                if isinstance(f, dict) and f.get("track_id"):
                    self._features_cache[f["track_id"]] = f

        return [self._features_cache[tid] for tid in track_ids if tid in self._features_cache]

    def record_skip(self, track: Track, mood: str) -> None:
        """Record that a track was skipped."""
        self.memory.record(
            track_id=track.id,
            track_name=track.name,
            artist=track.artist,
            action="skipped",
            mood=mood,
            energy=0.5,
        )

    def record_completion(self, track: Track, mood: str) -> None:
        """Record that a track was listened to completion."""
        self.memory.record(
            track_id=track.id,
            track_name=track.name,
            artist=track.artist,
            action="completed",
            mood=mood,
            energy=0.5,
        )

    def get_memory_stats(self) -> dict:
        """Get memory statistics for debugging/display."""
        return self.memory.get_stats()
