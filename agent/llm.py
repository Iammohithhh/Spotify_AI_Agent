"""
LLM integration for conversational AI.
Supports multiple providers with free tiers:
- Groq (Llama 3) - Fast, generous free tier
- Google Gemini - Good free tier
"""

import os
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Response from LLM."""
    content: str
    provider: str
    model: str
    success: bool = True
    error: str | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def chat(self, messages: list[dict], system_prompt: str | None = None) -> LLMResponse:
        """Send messages and get response."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and available."""
        pass


class GroqProvider(LLMProvider):
    """Groq API provider (Llama 3, free tier)."""

    def __init__(self, api_key: str | None = None, model: str = "llama-3.1-8b-instant"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None and self.api_key:
            try:
                from groq import Groq
                self._client = Groq(api_key=self.api_key)
            except ImportError:
                pass
        return self._client

    def is_available(self) -> bool:
        return self.api_key is not None and self._get_client() is not None

    def chat(self, messages: list[dict], system_prompt: str | None = None) -> LLMResponse:
        client = self._get_client()
        if not client:
            return LLMResponse(
                content="",
                provider="groq",
                model=self.model,
                success=False,
                error="Groq client not available",
            )

        try:
            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)

            response = client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                max_tokens=1024,
                temperature=0.7,
            )

            return LLMResponse(
                content=response.choices[0].message.content,
                provider="groq",
                model=self.model,
                success=True,
            )
        except Exception as e:
            return LLMResponse(
                content="",
                provider="groq",
                model=self.model,
                success=False,
                error=str(e),
            )


class GeminiProvider(LLMProvider):
    """Google Gemini provider (free tier)."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-1.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None and self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel(self.model)
            except ImportError:
                pass
        return self._client

    def is_available(self) -> bool:
        return self.api_key is not None and self._get_client() is not None

    def chat(self, messages: list[dict], system_prompt: str | None = None) -> LLMResponse:
        client = self._get_client()
        if not client:
            return LLMResponse(
                content="",
                provider="gemini",
                model=self.model,
                success=False,
                error="Gemini client not available",
            )

        try:
            # Convert messages to Gemini format
            prompt_parts = []
            if system_prompt:
                prompt_parts.append(f"System: {system_prompt}\n\n")

            for msg in messages:
                role = "User" if msg["role"] == "user" else "Assistant"
                prompt_parts.append(f"{role}: {msg['content']}\n")

            prompt_parts.append("Assistant:")
            full_prompt = "".join(prompt_parts)

            response = client.generate_content(full_prompt)

            return LLMResponse(
                content=response.text,
                provider="gemini",
                model=self.model,
                success=True,
            )
        except Exception as e:
            return LLMResponse(
                content="",
                provider="gemini",
                model=self.model,
                success=False,
                error=str(e),
            )


class ConversationalAgent:
    """
    Conversational agent that uses LLM for natural interactions.
    Falls back gracefully when LLM is not available.
    """

    SYSTEM_PROMPT = """You are a friendly music AI assistant integrated with YouTube Music/Spotify. You help users with music discovery, playback control, and music conversations.

CURRENT CONTEXT:
{context}

YOUR CAPABILITIES:
1. Play music by mood, language, artist, genre
2. Control playback (play, pause, next, previous, shuffle)
3. Answer questions about the currently playing song/artist
4. Provide music recommendations
5. Have casual conversations about music

RESPONSE FORMAT - Use these action tags when appropriate:
- [PLAY] - Resume playback
- [PAUSE] - Pause playback
- [NEXT] - Skip to next track
- [PREVIOUS] - Go to previous track
- [SHUFFLE] - Enable shuffle
- [SEARCH: query] - Search and play music (use descriptive query)
- [INFO] - User wants information (don't search, just respond)
- [STATS] - User wants their listening statistics

CRITICAL RULES:
1. If user asks "what song is this" or "what's playing" - describe the current track from context, use [INFO]
2. If user asks "tell me about this song/artist" - provide info about what's in context, use [INFO]
3. If user says "stats" or asks about their listening history - use [STATS]
4. If user wants to PLAY something new - use [SEARCH: descriptive query]
5. If user is just chatting or asking questions - respond naturally, use [INFO]
6. For podcasts, use [SEARCH: podcast topic intellectual discussion] format

EXAMPLES:
User: "What song is this?"
Response: Based on what's playing, this is "Song Name" by Artist. It's a popular track from their album... [INFO]

User: "Tell me about this artist"
Response: The artist currently playing is X. They are known for... [INFO]

User: "Play some sad Telugu songs"
Response: Let me find some emotional Telugu music for you. [SEARCH: sad Telugu emotional songs]

User: "Stats"
Response: [STATS]

User: "I'm feeling low"
Response: I understand. Let me play something soothing for you. [SEARCH: comforting relaxing melancholy music]

User: "Play intellectual podcast"
Response: Let me find a thought-provoking podcast for you. [SEARCH: intellectual discussion podcast educational]

Be concise (2-3 sentences). Be helpful and friendly.
"""

    def __init__(self, config=None):
        self.providers: list[LLMProvider] = []
        self._current_track: dict | None = None
        self._conversation_history: list[dict] = []

        # Initialize providers based on config or environment
        api_key = None
        if config and config.llm.api_key:
            api_key = config.llm.api_key

        # Try Groq first (faster), then Gemini
        self.providers.append(GroqProvider(api_key))
        self.providers.append(GeminiProvider(api_key))

    def set_current_track(self, track_info: dict | None):
        """Update current track context."""
        self._current_track = track_info

    def _get_context(self) -> str:
        """Build context string for LLM."""
        if self._current_track:
            return f"""Currently playing:
- Song: {self._current_track.get('name', 'Unknown')}
- Artist: {self._current_track.get('artist', 'Unknown')}
- Album: {self._current_track.get('album', 'Unknown')}"""
        return "No song currently playing."

    def _get_provider(self) -> LLMProvider | None:
        """Get first available provider."""
        for provider in self.providers:
            if provider.is_available():
                return provider
        return None

    def chat(self, user_message: str) -> tuple[str, dict | None]:
        """
        Process user message and return response.
        Returns: (response_text, action_dict or None)

        action_dict can be:
        - {"action": "play"}
        - {"action": "pause"}
        - {"action": "next"}
        - {"action": "search", "query": "..."}
        - None (just conversation)
        """
        provider = self._get_provider()

        if not provider:
            # Fallback to simple pattern matching
            return self._fallback_response(user_message)

        # Add to history
        self._conversation_history.append({"role": "user", "content": user_message})

        # Keep only last 10 messages for context
        if len(self._conversation_history) > 10:
            self._conversation_history = self._conversation_history[-10:]

        # Get LLM response
        system = self.SYSTEM_PROMPT.format(context=self._get_context())
        response = provider.chat(self._conversation_history, system_prompt=system)

        if not response.success:
            return self._fallback_response(user_message)

        # Parse response for actions
        content = response.content
        action = self._parse_action(content)

        # Clean action tags from response
        clean_content = self._clean_response(content)

        # Add to history
        self._conversation_history.append({"role": "assistant", "content": clean_content})

        return clean_content, action

    def _parse_action(self, text: str) -> dict | None:
        """Parse action from LLM response."""
        import re

        text_upper = text.upper()

        # Info/conversational - no playback action needed
        if "[INFO]" in text_upper:
            return {"action": "info"}
        if "[STATS]" in text_upper:
            return {"action": "stats"}

        # Playback controls
        if "[PLAY]" in text_upper:
            return {"action": "play"}
        if "[PAUSE]" in text_upper or "[STOP]" in text_upper:
            return {"action": "pause"}
        if "[NEXT]" in text_upper or "[SKIP]" in text_upper:
            return {"action": "next"}
        if "[PREVIOUS]" in text_upper or "[PREV]" in text_upper:
            return {"action": "previous"}
        if "[SHUFFLE]" in text_upper:
            return {"action": "shuffle"}

        # Search action
        search_match = re.search(r'\[SEARCH:\s*(.+?)\]', text, re.IGNORECASE)
        if search_match:
            return {"action": "search", "query": search_match.group(1).strip()}

        return None

    def _clean_response(self, text: str) -> str:
        """Remove action tags from response."""
        import re
        # Remove all bracketed actions
        text = re.sub(r'\[(?:PLAY|PAUSE|STOP|NEXT|SKIP|PREVIOUS|PREV|SHUFFLE|INFO|STATS)\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[SEARCH:\s*.+?\]', '', text, flags=re.IGNORECASE)
        return text.strip()

    def _fallback_response(self, text: str) -> tuple[str, dict | None]:
        """Simple fallback when LLM is not available."""
        text_lower = text.lower()

        # Stats request
        if text_lower in ["stats", "statistics", "my stats", "listening stats", "history"]:
            return "Here are your stats!", {"action": "stats"}

        # Info about current track
        if any(phrase in text_lower for phrase in [
            "what song", "what's playing", "current song", "what is this",
            "tell me about this", "info about this", "about this song",
            "who sings", "who is the artist", "what artist"
        ]):
            if self._current_track:
                name = self._current_track.get('name', 'Unknown')
                artist = self._current_track.get('artist', 'Unknown')
                album = self._current_track.get('album', '')
                response = f"Currently playing: {name} by {artist}"
                if album:
                    response += f" from the album '{album}'"
                return response, {"action": "info"}
            return "Nothing is playing right now. Ask me to play something!", {"action": "info"}

        # Playback controls
        if any(word in text_lower for word in ["pause", "stop"]):
            return "Paused!", {"action": "pause"}

        if any(word in text_lower for word in ["next", "skip"]):
            return "Skipping to next track!", {"action": "next"}

        if any(word in text_lower for word in ["previous", "back", "go back"]):
            return "Going back!", {"action": "previous"}

        if text_lower in ["resume", "continue", "unpause"]:
            return "Resuming!", {"action": "play"}

        if "shuffle" in text_lower:
            return "Shuffling!", {"action": "shuffle"}

        # Podcast search
        if "podcast" in text_lower:
            query = text_lower.replace("play", "").strip()
            if "intellectual" in text_lower or "educational" in text_lower:
                return "Finding an intellectual podcast for you!", {"action": "search", "query": "intellectual discussion podcast TED educational"}
            return f"Finding podcasts for you!", {"action": "search", "query": f"{query} podcast discussion"}

        # Music search with mood
        if any(word in text_lower for word in ["play", "want", "need", "some", "music", "songs", "feeling"]):
            # Extract mood/language
            moods = ["sad", "happy", "calm", "energetic", "chill", "romantic", "focus", "low", "melancholy"]
            languages = ["telugu", "hindi", "kannada", "tamil", "english", "korean", "spanish", "punjabi"]

            found_mood = next((m for m in moods if m in text_lower), None)
            found_lang = next((l for l in languages if l in text_lower), None)

            if found_mood or found_lang:
                query_parts = []
                if found_lang:
                    query_parts.append(found_lang)
                if found_mood:
                    # Map "low" to "sad"
                    query_parts.append("sad emotional" if found_mood == "low" else found_mood)
                query_parts.append("songs music")
                return f"Finding {' '.join(query_parts[:-1])} music!", {"action": "search", "query": " ".join(query_parts)}

            return "Finding music for you!", {"action": "search", "query": text}

        # Recommend/surprise
        if any(word in text_lower for word in ["recommend", "suggest", "surprise"]):
            return "Let me surprise you with something!", {"action": "search", "query": "popular trending music hits"}

        # Default - just chat
        return "I can help you play music! Try 'play sad Telugu songs' or 'what song is this?'", {"action": "info"}

    def clear_history(self):
        """Clear conversation history."""
        self._conversation_history = []


def get_song_info(track_name: str, artist: str) -> dict | None:
    """
    Fetch additional info about a song using web search or APIs.
    Returns dict with info or None if not found.
    """
    # This is a placeholder - in production, you'd use:
    # - Wikipedia API
    # - MusicBrainz API
    # - Last.fm API
    # - Or web search

    return {
        "name": track_name,
        "artist": artist,
        "info": "Song information would be fetched from music APIs.",
    }
