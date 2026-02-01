"""
Intent and mood parser.
Extracts structured intent from natural language input.
"""

import re
from dataclasses import dataclass, field
from enum import Enum


class ContentType(Enum):
    MUSIC = "music"
    PODCAST = "podcast"
    CONTROL = "control"  # play, pause, skip, etc.
    QUERY = "query"      # what's playing, etc.
    NOTE = "note"        # take note, save note, etc.
    RECOMMEND = "recommend"  # get recommendations
    UNKNOWN = "unknown"


class Mood(Enum):
    HAPPY = "happy"
    SAD = "sad"
    ENERGETIC = "energetic"
    CALM = "calm"
    ROMANTIC = "romantic"
    ANGRY = "angry"
    FOCUSED = "focused"
    CHILL = "chill"
    NEUTRAL = "neutral"


class ControlAction(Enum):
    PLAY = "play"
    PAUSE = "pause"
    RESUME = "resume"
    NEXT = "next"
    PREVIOUS = "previous"
    SHUFFLE = "shuffle"
    REPEAT = "repeat"
    QUEUE = "queue"
    NONE = "none"


@dataclass
class Intent:
    """Parsed intent from user message."""
    content_type: ContentType
    mood: Mood = Mood.NEUTRAL
    energy_level: float = 0.5  # 0.0 (low) to 1.0 (high)
    language: str | None = None
    genre: str | None = None
    artist: str | None = None
    control_action: ControlAction = ControlAction.NONE
    familiarity: str = "any"  # "high" (liked/known), "low" (discover), "any"
    raw_query: str = ""
    confidence: float = 1.0
    extras: dict = field(default_factory=dict)


class IntentParser:
    """Rule-based intent parser."""

    # Mood keywords mapping
    MOOD_KEYWORDS: dict[Mood, list[str]] = {
        Mood.HAPPY: ["happy", "joy", "cheerful", "upbeat", "good mood", "excited", "party"],
        Mood.SAD: ["sad", "low", "down", "depressed", "melancholy", "heartbreak", "crying", "emotional"],
        Mood.ENERGETIC: ["energetic", "pump", "workout", "gym", "running", "hype", "power", "intense"],
        Mood.CALM: ["calm", "peaceful", "relax", "chill", "mellow", "quiet", "soothing", "sleep", "night"],
        Mood.ROMANTIC: ["romantic", "love", "date", "crush", "heart"],
        Mood.ANGRY: ["angry", "rage", "frustrated", "mad", "aggressive"],
        Mood.FOCUSED: ["focus", "study", "work", "concentrate", "productive", "coding"],
        Mood.CHILL: ["chill", "vibe", "lofi", "lo-fi", "ambient"],
    }

    # Language keywords
    LANGUAGE_KEYWORDS: dict[str, list[str]] = {
        "telugu": ["telugu", "tollywood"],
        "kannada": ["kannada", "sandalwood"],
        "hindi": ["hindi", "bollywood"],
        "tamil": ["tamil", "kollywood"],
        "malayalam": ["malayalam", "mollywood"],
        "english": ["english", "western", "hollywood"],
        "korean": ["korean", "kpop", "k-pop"],
        "spanish": ["spanish", "latino", "reggaeton"],
        "punjabi": ["punjabi", "bhangra"],
    }

    # Control action patterns
    CONTROL_PATTERNS: dict[ControlAction, list[str]] = {
        ControlAction.PAUSE: [r"\bpause\b", r"\bstop\b"],
        ControlAction.RESUME: [r"\bresume\b", r"\bcontinue\b", r"\bunpause\b"],
        ControlAction.NEXT: [r"\bnext\b", r"\bskip\b"],
        ControlAction.PREVIOUS: [r"\bprevious\b", r"\bprev\b", r"\bback\b", r"\blast song\b"],
        ControlAction.SHUFFLE: [r"\bshuffle\b", r"\bmix\b"],
        ControlAction.QUEUE: [r"\bqueue\b", r"\badd to queue\b"],
    }

    # Query patterns
    QUERY_PATTERNS = [
        r"what.*(playing|song|track)",
        r"current.*(song|track)",
        r"now playing",
        r"what is this",
    ]

    # Podcast patterns
    PODCAST_PATTERNS = [
        r"\bpodcast\b",
        r"\bepisode\b",
        r"\bshow\b",
    ]

    # Note-taking patterns
    NOTE_PATTERNS = [
        r"\bnote\b",
        r"\bsave\b.*\b(note|thought|idea)\b",
        r"\bremember\b",
        r"\bkey (point|idea|takeaway)\b",
        r"\bwrite down\b",
        r"\badd note\b",
    ]

    # Recommendation patterns
    RECOMMEND_PATTERNS = [
        r"\brecommend\b",
        r"\bsuggest\b",
        r"\bwhat should i\b",
        r"\bsurprise me\b",
        r"\bsomething (new|different)\b",
        r"\bdiscover\b",
    ]

    def parse(self, text: str) -> Intent:
        """Parse user text into structured intent."""
        text_lower = text.lower().strip()

        # Check for control actions first
        control = self._detect_control(text_lower)
        if control != ControlAction.NONE:
            return Intent(
                content_type=ContentType.CONTROL,
                control_action=control,
                raw_query=text,
            )

        # Check for query
        if self._is_query(text_lower):
            return Intent(
                content_type=ContentType.QUERY,
                raw_query=text,
            )

        # Check for note-taking
        if self._is_note(text_lower):
            return Intent(
                content_type=ContentType.NOTE,
                raw_query=text,
                extras={"note_text": self._extract_note_content(text)},
            )

        # Check for recommendations
        if self._is_recommend(text_lower):
            return Intent(
                content_type=ContentType.RECOMMEND,
                raw_query=text,
                mood=self._detect_mood(text_lower),
                language=self._detect_language(text_lower),
            )

        # Check for podcast
        if self._is_podcast(text_lower):
            return Intent(
                content_type=ContentType.PODCAST,
                raw_query=text,
                mood=self._detect_mood(text_lower),
            )

        # Default: music request
        mood = self._detect_mood(text_lower)
        language = self._detect_language(text_lower)
        energy = self._mood_to_energy(mood)
        familiarity = self._detect_familiarity(text_lower)
        genre = self._detect_genre(text_lower)
        artist = self._detect_artist(text_lower)

        return Intent(
            content_type=ContentType.MUSIC,
            mood=mood,
            energy_level=energy,
            language=language,
            genre=genre,
            artist=artist,
            familiarity=familiarity,
            raw_query=text,
            confidence=self._calculate_confidence(mood, language, genre, artist),
        )

    def _detect_control(self, text: str) -> ControlAction:
        """Detect playback control intent."""
        for action, patterns in self.CONTROL_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return action
        return ControlAction.NONE

    def _is_query(self, text: str) -> bool:
        """Check if text is a query about current playback."""
        return any(re.search(p, text, re.IGNORECASE) for p in self.QUERY_PATTERNS)

    def _is_podcast(self, text: str) -> bool:
        """Check if text mentions podcasts."""
        return any(re.search(p, text, re.IGNORECASE) for p in self.PODCAST_PATTERNS)

    def _is_note(self, text: str) -> bool:
        """Check if text is a note-taking request."""
        return any(re.search(p, text, re.IGNORECASE) for p in self.NOTE_PATTERNS)

    def _is_recommend(self, text: str) -> bool:
        """Check if text is a recommendation request."""
        return any(re.search(p, text, re.IGNORECASE) for p in self.RECOMMEND_PATTERNS)

    def _extract_note_content(self, text: str) -> str:
        """Extract the actual note content from text."""
        # Remove common prefixes
        prefixes = [
            r"^(add\s+)?note:?\s*",
            r"^save\s+(this\s+)?note:?\s*",
            r"^remember:?\s*",
            r"^write\s+down:?\s*",
        ]
        result = text
        for prefix in prefixes:
            result = re.sub(prefix, "", result, flags=re.IGNORECASE)
        return result.strip()

    def _detect_mood(self, text: str) -> Mood:
        """Detect mood from text."""
        scores: dict[Mood, int] = {}

        for mood, keywords in self.MOOD_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[mood] = score

        if scores:
            return max(scores, key=scores.get)  # type: ignore
        return Mood.NEUTRAL

    def _detect_language(self, text: str) -> str | None:
        """Detect language preference from text."""
        for lang, keywords in self.LANGUAGE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return lang
        return None

    def _detect_familiarity(self, text: str) -> str:
        """Detect if user wants familiar or new music."""
        familiar_keywords = ["liked", "favorite", "my songs", "saved", "known", "familiar"]
        discover_keywords = ["new", "discover", "explore", "recommend", "suggestion"]

        if any(kw in text for kw in familiar_keywords):
            return "high"
        if any(kw in text for kw in discover_keywords):
            return "low"
        return "any"

    def _detect_genre(self, text: str) -> str | None:
        """Detect music genre from text."""
        genres = [
            "pop", "rock", "jazz", "classical", "hip hop", "hip-hop", "rap",
            "r&b", "rnb", "electronic", "edm", "metal", "country", "folk",
            "indie", "alternative", "blues", "soul", "funk", "reggae",
            "lofi", "lo-fi", "acoustic", "instrumental",
        ]
        for genre in genres:
            if genre in text:
                return genre
        return None

    def _detect_artist(self, text: str) -> str | None:
        """
        Detect artist name from text.
        Basic implementation - looks for "by <artist>" or "from <artist>" patterns.
        """
        patterns = [
            r"by\s+([a-zA-Z\s]+?)(?:\s+songs?|\s+music|$)",
            r"from\s+([a-zA-Z\s]+?)(?:\s+songs?|\s+music|$)",
            r"([a-zA-Z\s]+?)\s+songs?",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                artist = match.group(1).strip()
                # Filter out mood/common words
                skip_words = {"sad", "happy", "calm", "some", "good", "nice", "play"}
                if artist.lower() not in skip_words and len(artist) > 2:
                    return artist
        return None

    def _mood_to_energy(self, mood: Mood) -> float:
        """Map mood to energy level."""
        energy_map = {
            Mood.HAPPY: 0.7,
            Mood.SAD: 0.3,
            Mood.ENERGETIC: 0.9,
            Mood.CALM: 0.2,
            Mood.ROMANTIC: 0.4,
            Mood.ANGRY: 0.85,
            Mood.FOCUSED: 0.5,
            Mood.CHILL: 0.3,
            Mood.NEUTRAL: 0.5,
        }
        return energy_map.get(mood, 0.5)

    def _calculate_confidence(
        self,
        mood: Mood,
        language: str | None,
        genre: str | None,
        artist: str | None,
    ) -> float:
        """Calculate confidence score based on extracted info."""
        score = 0.5  # Base
        if mood != Mood.NEUTRAL:
            score += 0.2
        if language:
            score += 0.15
        if genre:
            score += 0.1
        if artist:
            score += 0.1
        return min(score, 1.0)
