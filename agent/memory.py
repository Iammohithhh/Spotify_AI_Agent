"""
Memory engine for learning user preferences.
Stores and retrieves song interactions, mood associations, and listening patterns.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Literal


ActionType = Literal["played", "skipped", "replayed", "completed", "queued"]


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
    context: dict = field(default_factory=dict)  # Additional context like time of day

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        return cls(**data)


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
    ) -> None:
        """Record a track interaction."""
        entry = MemoryEntry(
            track_id=track_id,
            track_name=track_name,
            artist=artist,
            action=action,
            mood=mood,
            language=language,
            energy=energy,
            timestamp=datetime.now().isoformat(),
            context=context or {},
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
