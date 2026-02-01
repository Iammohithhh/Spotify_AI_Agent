"""
Memory engine for learning user preferences.
Stores and retrieves song interactions, mood associations, and listening patterns.
Enhanced with time-based patterns and recommendation scoring.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from collections import defaultdict


ActionType = Literal["played", "skipped", "replayed", "completed", "queued", "liked"]


def get_time_of_day() -> str:
    """Get current time of day category."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    else:
        return "night"


def get_day_type() -> str:
    """Get day type (weekday/weekend)."""
    return "weekend" if datetime.now().weekday() >= 5 else "weekday"


@dataclass
class MemoryEntry:
    """A single memory entry for a track interaction."""
    track_id: str
    track_name: str
    artist: str
    action: ActionType
    mood: str
    language: str | None
    energy: float
    timestamp: str
    context: dict = field(default_factory=dict)  # time_of_day, day_type, query, etc.

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        return cls(**data)

    @property
    def age_days(self) -> float:
        """Get age of entry in days."""
        try:
            entry_time = datetime.fromisoformat(self.timestamp)
            return (datetime.now() - entry_time).total_seconds() / 86400
        except ValueError:
            return 30  # Default to old if can't parse


@dataclass
class TrackScore:
    """Aggregated score for a track."""
    track_id: str
    track_name: str
    artist: str
    score: float
    play_count: int
    skip_count: int
    last_played: str
    moods: list[str]
    languages: list[str]


@dataclass
class MoodProfile:
    """Aggregated profile for a mood."""
    mood: str
    track_ids: list[str]
    avg_energy: float
    play_count: int
    skip_count: int
    languages: dict[str, int]  # language -> count

    @property
    def preference_score(self) -> float:
        """Calculate preference score (higher = better)."""
        if self.play_count + self.skip_count == 0:
            return 0.5
        return self.play_count / (self.play_count + self.skip_count)


class Memory:
    """
    Persistent memory engine.
    Learns from user interactions and provides context for recommendations.
    """

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.entries: list[MemoryEntry] = []
        self._load()

    def _load(self) -> None:
        """Load memory from disk."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    self.entries = [MemoryEntry.from_dict(e) for e in data]
            except (json.JSONDecodeError, KeyError):
                self.entries = []
        else:
            self.entries = []

    def _save(self) -> None:
        """Persist memory to disk."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w") as f:
            json.dump([e.to_dict() for e in self.entries], f, indent=2)

    def record(
        self,
        track_id: str,
        track_name: str,
        artist: str,
        action: ActionType,
        mood: str,
        language: str | None = None,
        energy: float = 0.5,
        context: dict | None = None,
        query: str | None = None,
    ) -> None:
        """Record a track interaction with rich context."""
        # Build context with time patterns
        full_context = {
            "time_of_day": get_time_of_day(),
            "day_type": get_day_type(),
            "hour": datetime.now().hour,
            **(context or {}),
        }
        if query:
            full_context["query"] = query

        entry = MemoryEntry(
            track_id=track_id,
            track_name=track_name,
            artist=artist,
            action=action,
            mood=mood,
            language=language,
            energy=energy,
            timestamp=datetime.now().isoformat(),
            context=full_context,
        )
        self.entries.append(entry)
        self._save()

    def get_tracks_for_mood(self, mood: str, limit: int = 20) -> list[str]:
        """
        Get track IDs that were positively associated with a mood.
        Prioritizes replayed and completed tracks, excludes frequently skipped.
        """
        mood_entries = [e for e in self.entries if e.mood == mood]

        # Count positive vs negative signals per track
        track_scores: dict[str, float] = {}
        for entry in mood_entries:
            track_id = entry.track_id
            if track_id not in track_scores:
                track_scores[track_id] = 0

            if entry.action == "replayed":
                track_scores[track_id] += 2
            elif entry.action == "completed":
                track_scores[track_id] += 1
            elif entry.action == "played":
                track_scores[track_id] += 0.5
            elif entry.action == "skipped":
                track_scores[track_id] -= 1

        # Sort by score and return top tracks
        sorted_tracks = sorted(track_scores.items(), key=lambda x: x[1], reverse=True)
        return [t[0] for t, score in sorted_tracks if score > 0][:limit]

    def get_tracks_for_language(self, language: str, limit: int = 20) -> list[str]:
        """Get track IDs associated with a language."""
        lang_entries = [e for e in self.entries if e.language == language]

        track_scores: dict[str, float] = {}
        for entry in lang_entries:
            track_id = entry.track_id
            if track_id not in track_scores:
                track_scores[track_id] = 0

            if entry.action in ("replayed", "completed", "played"):
                track_scores[track_id] += 1
            elif entry.action == "skipped":
                track_scores[track_id] -= 0.5

        sorted_tracks = sorted(track_scores.items(), key=lambda x: x[1], reverse=True)
        return [t[0] for t, score in sorted_tracks if score > 0][:limit]

    def get_mood_profile(self, mood: str) -> MoodProfile:
        """Get aggregated profile for a mood."""
        mood_entries = [e for e in self.entries if e.mood == mood]

        if not mood_entries:
            return MoodProfile(
                mood=mood,
                track_ids=[],
                avg_energy=0.5,
                play_count=0,
                skip_count=0,
                languages={},
            )

        track_ids = list(set(e.track_id for e in mood_entries))
        avg_energy = sum(e.energy for e in mood_entries) / len(mood_entries)
        play_count = sum(1 for e in mood_entries if e.action in ("played", "completed", "replayed"))
        skip_count = sum(1 for e in mood_entries if e.action == "skipped")

        languages: dict[str, int] = {}
        for e in mood_entries:
            if e.language:
                languages[e.language] = languages.get(e.language, 0) + 1

        return MoodProfile(
            mood=mood,
            track_ids=track_ids,
            avg_energy=avg_energy,
            play_count=play_count,
            skip_count=skip_count,
            languages=languages,
        )

    def get_recent_tracks(self, limit: int = 10) -> list[str]:
        """Get recently interacted track IDs."""
        # Sort by timestamp descending
        sorted_entries = sorted(
            self.entries,
            key=lambda e: e.timestamp,
            reverse=True,
        )
        seen = set()
        recent = []
        for entry in sorted_entries:
            if entry.track_id not in seen:
                recent.append(entry.track_id)
                seen.add(entry.track_id)
            if len(recent) >= limit:
                break
        return recent

    def get_favorite_artists(self, limit: int = 5) -> list[str]:
        """Get most frequently played artists."""
        artist_counts: dict[str, int] = {}
        for entry in self.entries:
            if entry.action in ("played", "completed", "replayed"):
                artist_counts[entry.artist] = artist_counts.get(entry.artist, 0) + 1

        sorted_artists = sorted(artist_counts.items(), key=lambda x: x[1], reverse=True)
        return [a for a, _ in sorted_artists[:limit]]

    def get_stats(self) -> dict:
        """Get memory statistics."""
        moods = {}
        languages = {}
        actions = {}

        for entry in self.entries:
            moods[entry.mood] = moods.get(entry.mood, 0) + 1
            if entry.language:
                languages[entry.language] = languages.get(entry.language, 0) + 1
            actions[entry.action] = actions.get(entry.action, 0) + 1

        return {
            "total_entries": len(self.entries),
            "unique_tracks": len(set(e.track_id for e in self.entries)),
            "moods": moods,
            "languages": languages,
            "actions": actions,
        }

    def clear(self) -> None:
        """Clear all memory (use with caution)."""
        self.entries = []
        self._save()

    # -------------------------------------------------------------------------
    # Advanced Recommendation Methods
    # -------------------------------------------------------------------------

    def get_time_based_recommendations(self, limit: int = 20) -> list[str]:
        """
        Get recommendations based on current time patterns.
        Returns tracks commonly played at this time of day.
        """
        current_time = get_time_of_day()
        current_day = get_day_type()

        # Find tracks played at similar times
        time_matches = [
            e for e in self.entries
            if e.context.get("time_of_day") == current_time
            and e.action in ("played", "completed", "replayed")
        ]

        # Score by frequency and recency
        track_scores: dict[str, float] = defaultdict(float)
        for entry in time_matches:
            # Base score
            score = 1.0
            if entry.action == "replayed":
                score = 2.0
            elif entry.action == "completed":
                score = 1.5

            # Recency boost (decay over 30 days)
            age = entry.age_days
            recency_factor = max(0.1, 1.0 - (age / 30))
            score *= recency_factor

            # Day type bonus
            if entry.context.get("day_type") == current_day:
                score *= 1.2

            track_scores[entry.track_id] += score

        # Sort and return
        sorted_tracks = sorted(track_scores.items(), key=lambda x: -x[1])
        return [tid for tid, _ in sorted_tracks[:limit]]

    def get_similar_mood_tracks(self, mood: str, limit: int = 20) -> list[TrackScore]:
        """
        Get tracks with detailed scoring for a mood.
        Returns TrackScore objects with full metadata.
        """
        mood_entries = [e for e in self.entries if e.mood == mood]

        # Aggregate by track
        track_data: dict[str, dict] = {}
        for entry in mood_entries:
            tid = entry.track_id
            if tid not in track_data:
                track_data[tid] = {
                    "track_name": entry.track_name,
                    "artist": entry.artist,
                    "plays": 0,
                    "skips": 0,
                    "score": 0.0,
                    "last_played": entry.timestamp,
                    "moods": set(),
                    "languages": set(),
                }

            data = track_data[tid]

            # Count actions
            if entry.action == "skipped":
                data["skips"] += 1
                data["score"] -= 1.0
            elif entry.action == "replayed":
                data["plays"] += 1
                data["score"] += 2.5
            elif entry.action == "completed":
                data["plays"] += 1
                data["score"] += 1.5
            elif entry.action == "played":
                data["plays"] += 1
                data["score"] += 0.5
            elif entry.action == "liked":
                data["score"] += 3.0

            # Track moods and languages
            data["moods"].add(entry.mood)
            if entry.language:
                data["languages"].add(entry.language)

            # Update last played
            if entry.timestamp > data["last_played"]:
                data["last_played"] = entry.timestamp

        # Convert to TrackScore objects
        results = []
        for tid, data in track_data.items():
            if data["score"] > 0:  # Only positive scores
                results.append(TrackScore(
                    track_id=tid,
                    track_name=data["track_name"],
                    artist=data["artist"],
                    score=data["score"],
                    play_count=data["plays"],
                    skip_count=data["skips"],
                    last_played=data["last_played"],
                    moods=list(data["moods"]),
                    languages=list(data["languages"]),
                ))

        # Sort by score
        results.sort(key=lambda x: -x.score)
        return results[:limit]

    def get_artist_affinity(self) -> dict[str, float]:
        """
        Get user's affinity scores for artists.
        Higher score = user likes this artist more.
        """
        artist_scores: dict[str, float] = defaultdict(float)
        artist_plays: dict[str, int] = defaultdict(int)

        for entry in self.entries:
            artist = entry.artist
            artist_plays[artist] += 1

            if entry.action == "skipped":
                artist_scores[artist] -= 0.5
            elif entry.action in ("played", "completed"):
                artist_scores[artist] += 1.0
            elif entry.action == "replayed":
                artist_scores[artist] += 2.0
            elif entry.action == "liked":
                artist_scores[artist] += 3.0

        # Normalize by play count
        for artist in artist_scores:
            if artist_plays[artist] > 0:
                artist_scores[artist] /= artist_plays[artist]

        return dict(artist_scores)

    def get_language_preferences(self) -> dict[str, float]:
        """Get user's language preferences as scores."""
        lang_scores: dict[str, float] = defaultdict(float)
        lang_counts: dict[str, int] = defaultdict(int)

        for entry in self.entries:
            if entry.language:
                lang_counts[entry.language] += 1
                if entry.action in ("played", "completed", "replayed", "liked"):
                    lang_scores[entry.language] += 1.0
                elif entry.action == "skipped":
                    lang_scores[entry.language] -= 0.3

        # Normalize
        total = sum(lang_counts.values()) or 1
        return {lang: count / total for lang, count in lang_counts.items()}

    def get_listening_patterns(self) -> dict:
        """
        Analyze listening patterns for insights.
        Returns patterns by time, mood, language, etc.
        """
        patterns = {
            "by_time_of_day": defaultdict(int),
            "by_day_type": defaultdict(int),
            "by_hour": defaultdict(int),
            "mood_by_time": defaultdict(lambda: defaultdict(int)),
            "total_listening_sessions": 0,
            "avg_tracks_per_session": 0,
        }

        for entry in self.entries:
            if entry.action in ("played", "completed", "replayed"):
                time_of_day = entry.context.get("time_of_day", "unknown")
                day_type = entry.context.get("day_type", "unknown")
                hour = entry.context.get("hour", 0)

                patterns["by_time_of_day"][time_of_day] += 1
                patterns["by_day_type"][day_type] += 1
                patterns["by_hour"][hour] += 1
                patterns["mood_by_time"][time_of_day][entry.mood] += 1

        # Convert defaultdicts to regular dicts
        patterns["by_time_of_day"] = dict(patterns["by_time_of_day"])
        patterns["by_day_type"] = dict(patterns["by_day_type"])
        patterns["by_hour"] = dict(patterns["by_hour"])
        patterns["mood_by_time"] = {k: dict(v) for k, v in patterns["mood_by_time"].items()}

        return patterns

    def suggest_mood_for_time(self) -> str | None:
        """
        Suggest a mood based on current time patterns.
        Returns the mood most commonly listened to at this time.
        """
        current_time = get_time_of_day()

        mood_counts: dict[str, int] = defaultdict(int)
        for entry in self.entries:
            if entry.context.get("time_of_day") == current_time:
                if entry.action in ("played", "completed", "replayed"):
                    mood_counts[entry.mood] += 1

        if not mood_counts:
            return None

        return max(mood_counts.items(), key=lambda x: x[1])[0]

    def export_insights(self) -> dict:
        """Export all insights for display or analysis."""
        return {
            "stats": self.get_stats(),
            "patterns": self.get_listening_patterns(),
            "artist_affinity": dict(sorted(
                self.get_artist_affinity().items(),
                key=lambda x: -x[1]
            )[:10]),
            "language_preferences": self.get_language_preferences(),
            "suggested_mood": self.suggest_mood_for_time(),
            "favorite_artists": self.get_favorite_artists(limit=10),
        }
