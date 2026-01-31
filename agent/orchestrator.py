"""
Agent Orchestrator - The core brain of the system.
Coordinates intent parsing, memory, and Spotify actions.
"""

from dataclasses import dataclass
from pathlib import Path

from agent.intent_parser import Intent, IntentParser, ContentType, ControlAction, Mood
from agent.memory import Memory
from tools.spotify import SpotifyClient, Track, AudioFeatures
from config import Config


@dataclass
class AgentResponse:
    """Response from the agent."""
    message: str
    tracks_played: list[Track] | None = None
    action_taken: str | None = None
    success: bool = True


class Agent:
    """
    The main agent that orchestrates all components.
    This is the single entry point for user interactions.
    """

    def __init__(self, config: Config, spotify: SpotifyClient):
        self.config = config
        self.spotify = spotify
        self.parser = IntentParser()
        self.memory = Memory(config.data_dir / "memory.json")

        # Cache for audio features to avoid repeated API calls
        self._features_cache: dict[str, AudioFeatures] = {}

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

        if action == ControlAction.PAUSE:
            success = self.spotify.pause()
            return AgentResponse(
                message="Paused." if success else "Couldn't pause. Is Spotify open?",
                action_taken="pause",
                success=success,
            )

        elif action == ControlAction.RESUME:
            success = self.spotify.resume()
            return AgentResponse(
                message="Resuming." if success else "Couldn't resume. Is Spotify open?",
                action_taken="resume",
                success=success,
            )

        elif action == ControlAction.NEXT:
            success = self.spotify.next_track()
            # Record skip in memory if we know what was playing
            if success:
                state = self.spotify.get_playback_state()
                # Note: The skip already happened, so current track is the NEW track
                # We'd need to track previous track separately for accurate skip recording
            return AgentResponse(
                message="Skipped." if success else "Couldn't skip.",
                action_taken="next",
                success=success,
            )

        elif action == ControlAction.PREVIOUS:
            success = self.spotify.previous_track()
            return AgentResponse(
                message="Going back." if success else "Couldn't go back.",
                action_taken="previous",
                success=success,
            )

        elif action == ControlAction.SHUFFLE:
            # Toggle shuffle
            state = self.spotify.get_playback_state()
            if state:
                new_state = not state.shuffle
                success = self.spotify.set_shuffle(new_state)
                msg = f"Shuffle {'on' if new_state else 'off'}."
            else:
                success = self.spotify.set_shuffle(True)
                msg = "Shuffle on."
            return AgentResponse(message=msg if success else "Couldn't change shuffle.", success=success)

        return AgentResponse(message="Unknown control command.", success=False)

    def _handle_query(self, intent: Intent) -> AgentResponse:
        """Handle queries about current playback."""
        state = self.spotify.get_playback_state()

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
        episode = self.spotify.get_current_episode()

        if episode:
            progress_pct = int((episode["progress_ms"] / episode["duration_ms"]) * 100)
            return AgentResponse(
                message=f"Listening to: {episode['name']} ({episode['show']})\nProgress: {progress_pct}%",
                action_taken="podcast_query",
            )

        # Show saved podcasts
        shows = self.spotify.get_saved_shows(limit=5)
        if shows:
            show_list = "\n".join(f"  • {s['name']}" for s in shows)
            return AgentResponse(
                message=f"Your saved podcasts:\n{show_list}",
                action_taken="podcast_list",
            )

        return AgentResponse(
            message="No podcasts playing. Save some shows on Spotify first.",
            success=False,
        )

    def _handle_music(self, intent: Intent) -> AgentResponse:
        """Handle music requests - the main feature."""

        # Step 1: Gather candidate tracks
        candidates = self._gather_candidates(intent)

        if not candidates:
            return AgentResponse(
                message="Couldn't find matching tracks. Try being more specific or check your Spotify library.",
                success=False,
            )

        # Step 2: Filter and rank based on intent
        ranked_tracks = self._rank_tracks(candidates, intent)

        if not ranked_tracks:
            return AgentResponse(
                message="Found tracks but none matched your mood. Playing what I found anyway.",
                tracks_played=candidates[:10],
                success=True,
            )

        # Step 3: Play tracks
        track_uris = [t.uri for t in ranked_tracks[:20]]  # Limit to 20
        success = self.spotify.play_tracks(track_uris)

        if not success:
            # Check if it's a device issue
            devices = self.spotify.get_devices()
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
        for track in ranked_tracks[:5]:  # Record top 5 as "played"
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

        return AgentResponse(
            message=f"Playing{mood_desc}{lang_desc}: {first_track.name} by {first_track.artist} (+{count - 1} more)",
            tracks_played=ranked_tracks[:10],
            action_taken="play_music",
            success=True,
        )

    def _gather_candidates(self, intent: Intent) -> list[Track]:
        """Gather candidate tracks based on intent."""
        candidates: list[Track] = []

        # If artist specified, search for artist
        if intent.artist:
            search_query = f"artist:{intent.artist}"
            if intent.language:
                search_query += f" {intent.language}"
            candidates.extend(self.spotify.search_tracks(search_query, limit=30))

        # If high familiarity requested, prioritize liked songs
        if intent.familiarity == "high":
            liked = self.spotify.get_liked_songs(limit=100)
            candidates.extend(liked)

        # Check memory for mood-associated tracks
        if intent.mood != Mood.NEUTRAL:
            mood_track_ids = self.memory.get_tracks_for_mood(intent.mood.value, limit=20)
            # We'd need to fetch these tracks by ID, but that's expensive
            # For now, we use them to boost ranking later

        # If language specified, search by language
        if intent.language:
            lang_query = f"{intent.language} {intent.mood.value if intent.mood != Mood.NEUTRAL else ''}"
            candidates.extend(self.spotify.search_tracks(lang_query.strip(), limit=30))

        # If we still don't have enough, use recently played and top tracks
        if len(candidates) < 20:
            candidates.extend(self.spotify.get_recently_played(limit=30))
            candidates.extend(self.spotify.get_top_tracks(limit=30))

        # If still nothing and we have a mood, search by mood
        if len(candidates) < 10 and intent.mood != Mood.NEUTRAL:
            mood_query = intent.mood.value + " music"
            candidates.extend(self.spotify.search_tracks(mood_query, limit=20))

        # Deduplicate by track ID
        seen = set()
        unique = []
        for track in candidates:
            if track.id not in seen:
                seen.add(track.id)
                unique.append(track)

        return unique

    def _rank_tracks(self, tracks: list[Track], intent: Intent) -> list[Track]:
        """Rank tracks based on how well they match the intent."""
        if not tracks:
            return []

        # Get audio features for filtering
        track_ids = [t.id for t in tracks]
        features_list = self._get_features(track_ids)
        features_map = {f.track_id: f for f in features_list}

        # Get tracks that performed well for this mood from memory
        good_track_ids = set()
        if intent.mood != Mood.NEUTRAL:
            good_track_ids = set(self.memory.get_tracks_for_mood(intent.mood.value, limit=50))

        # Score each track
        scored: list[tuple[Track, float]] = []

        for track in tracks:
            score = 0.0
            features = features_map.get(track.id)

            # Boost if track was good for this mood before
            if track.id in good_track_ids:
                score += 3.0

            # Match energy level
            if features:
                energy_diff = abs(features.energy - intent.energy_level)
                score += (1 - energy_diff) * 2  # Up to 2 points for energy match

                # Match valence for happy/sad moods
                if intent.mood == Mood.SAD and features.valence < 0.4:
                    score += 1.5
                elif intent.mood == Mood.HAPPY and features.valence > 0.6:
                    score += 1.5
                elif intent.mood == Mood.CALM and features.energy < 0.4:
                    score += 1.5
                elif intent.mood == Mood.ENERGETIC and features.energy > 0.7:
                    score += 1.5

            # Popularity as tiebreaker
            score += track.popularity / 200  # Small boost, max 0.5

            scored.append((track, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        return [t for t, _ in scored]

    def _get_features(self, track_ids: list[str]) -> list[AudioFeatures]:
        """Get audio features with caching."""
        uncached = [tid for tid in track_ids if tid not in self._features_cache]

        if uncached:
            new_features = self.spotify.get_audio_features(uncached)
            for f in new_features:
                self._features_cache[f.track_id] = f

        return [self._features_cache[tid] for tid in track_ids if tid in self._features_cache]

    def record_skip(self, track: Track, mood: str) -> None:
        """Record that a track was skipped (called externally when skip detected)."""
        self.memory.record(
            track_id=track.id,
            track_name=track.name,
            artist=track.artist,
            action="skipped",
            mood=mood,
            energy=0.5,  # Unknown
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
