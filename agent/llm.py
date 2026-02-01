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

    SYSTEM_PROMPT = """You are a friendly music AI assistant. You help users with:
- Playing music based on mood, language, or artist
- Answering questions about songs, artists, and albums
- Providing music recommendations
- Having casual conversations about music

Current context:
{context}

Guidelines:
- Be concise but helpful (2-3 sentences usually)
- If asked about the current song, use the provided context
- For playback commands (play, pause, next), respond with the ACTION in brackets like [PLAY], [PAUSE], [NEXT], [SEARCH: query]
- For music requests, respond with [SEARCH: descriptive query]
- Be conversational and friendly
- If you don't know something specific about a song/artist, say so honestly
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
        text = re.sub(r'\[(?:PLAY|PAUSE|STOP|NEXT|SKIP|PREVIOUS|PREV|SHUFFLE)\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[SEARCH:\s*.+?\]', '', text, flags=re.IGNORECASE)
        return text.strip()

    def _fallback_response(self, text: str) -> tuple[str, dict | None]:
        """Simple fallback when LLM is not available."""
        text_lower = text.lower()

        # Simple pattern matching
        if any(word in text_lower for word in ["play", "start", "resume"]):
            if any(word in text_lower for word in ["sad", "happy", "calm", "energetic", "chill"]):
                # Extract mood
                for mood in ["sad", "happy", "calm", "energetic", "chill", "romantic", "focus"]:
                    if mood in text_lower:
                        return f"Let me find some {mood} music for you!", {"action": "search", "query": f"{mood} music"}
            return "Resuming playback!", {"action": "play"}

        if any(word in text_lower for word in ["pause", "stop"]):
            return "Paused!", {"action": "pause"}

        if any(word in text_lower for word in ["next", "skip"]):
            return "Skipping to next track!", {"action": "next"}

        if any(word in text_lower for word in ["previous", "back", "last"]):
            return "Going back!", {"action": "previous"}

        if "what" in text_lower and any(word in text_lower for word in ["playing", "song", "this"]):
            if self._current_track:
                return f"Currently playing: {self._current_track.get('name', 'Unknown')} by {self._current_track.get('artist', 'Unknown')}", None
            return "Nothing is playing right now.", None

        # Music search
        if any(word in text_lower for word in ["play", "want", "need", "some", "music", "songs"]):
            # Try to extract a search query
            return "I'll find something for you!", {"action": "search", "query": text}

        # Default
        return "I can help you play music! Try asking for a mood (like 'play sad songs') or an artist.", None

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
