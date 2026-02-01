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

    SYSTEM_PROMPT = """You are MusicBuddy, a friendly AI music assistant. You can control YouTube Music/Spotify and chat about music.

CURRENT CONTEXT:
{context}

ACTION TAGS (use exactly ONE at the end of your response):
- [CHAT] - For greetings, casual chat, questions about you, non-music conversations
- [INFO] - For questions about current song/artist (use info from context)
- [STATS] - When user wants listening history/statistics
- [PLAY] - Resume paused playback
- [PAUSE] - Pause current playback
- [NEXT] - Skip to next track
- [PREVIOUS] - Go back one track
- [SHUFFLE] - Enable shuffle mode
- [SEARCH: query] - ONLY when user explicitly wants to play NEW music

DECISION TREE (follow strictly):
1. Is user greeting or chatting casually? → Respond warmly + [CHAT]
2. Is user asking about YOU (name, capabilities)? → Introduce yourself + [CHAT]
3. Is user asking about CURRENT song/artist? → Use context info + [INFO]
4. Is user asking for stats/history? → [STATS]
5. Is user giving playback commands? → Execute + appropriate control tag
6. Is user explicitly requesting to PLAY/FIND music? → [SEARCH: query]
7. Anything else (feelings, thoughts) → Respond empathetically + [CHAT]

CRITICAL - DO NOT SEARCH when user:
- Says "info", "tell me about", "what is this", "who sings this" → [INFO]
- Says "hi", "hello", "chat", "talk to me", "what's your name" → [CHAT]
- Shares feelings WITHOUT asking for music → [CHAT]
- Asks questions about music theory/history → [INFO] or [CHAT]

ONLY use [SEARCH] when user says:
- "play", "find", "put on", "I want to listen to", "queue up"
- Explicitly names songs/artists they want to hear

EXAMPLES:
User: "What's your name?"
Response: I'm MusicBuddy, your AI music assistant! I can play music, answer questions about songs, and chat with you about music. What would you like to do? [CHAT]

User: "Information about this song"
Response: {answer based on context - song name, artist, album info} [INFO]

User: "I'm feeling cool today"
Response: That's great to hear! Glad you're in a good mood. Would you like me to play some music to match your vibe? [CHAT]

User: "Play some sad Telugu songs"
Response: Finding some emotional Telugu music for you! [SEARCH: sad Telugu emotional songs]

User: "Stats"
Response: Let me show you your listening statistics! [STATS]

User: "Who is the artist?"
Response: {use context to describe the artist currently playing} [INFO]

Be concise, friendly, and ALWAYS end with exactly one action tag.
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

        # Chat/conversational - just respond, no music action
        if "[CHAT]" in text_upper:
            return {"action": "chat"}

        # Info about current track - no playback action needed
        if "[INFO]" in text_upper:
            return {"action": "info"}

        # Stats request
        if "[STATS]" in text_upper:
            return {"action": "stats"}

        # Playback controls
        if "[PLAY]" in text_upper and "[SEARCH" not in text_upper:
            return {"action": "play"}
        if "[PAUSE]" in text_upper or "[STOP]" in text_upper:
            return {"action": "pause"}
        if "[NEXT]" in text_upper or "[SKIP]" in text_upper:
            return {"action": "next"}
        if "[PREVIOUS]" in text_upper or "[PREV]" in text_upper:
            return {"action": "previous"}
        if "[SHUFFLE]" in text_upper:
            return {"action": "shuffle"}

        # Search action - ONLY if explicitly tagged
        search_match = re.search(r'\[SEARCH:\s*(.+?)\]', text, re.IGNORECASE)
        if search_match:
            return {"action": "search", "query": search_match.group(1).strip()}

        # Default to chat if no action found (don't default to search!)
        return {"action": "chat"}

    def _clean_response(self, text: str) -> str:
        """Remove action tags from response."""
        import re
        # Remove all bracketed actions
        text = re.sub(r'\[(?:PLAY|PAUSE|STOP|NEXT|SKIP|PREVIOUS|PREV|SHUFFLE|INFO|STATS|CHAT)\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[SEARCH:\s*.+?\]', '', text, flags=re.IGNORECASE)
        return text.strip()

    def _fallback_response(self, text: str) -> tuple[str, dict | None]:
        """Smart fallback when LLM is not available."""
        text_lower = text.lower().strip()

        # ═══════════════════════════════════════════════════════════════════════
        # GREETINGS & CASUAL CHAT (No music action)
        # ═══════════════════════════════════════════════════════════════════════
        greetings = ["hi", "hello", "hey", "hola", "namaste", "yo", "sup", "howdy"]
        if text_lower in greetings or text_lower.startswith(tuple(f"{g} " for g in greetings)):
            return "Hey there! I'm MusicBuddy, your AI music assistant. I can play music, tell you about songs, and chat about music. What would you like?", {"action": "chat"}

        # Questions about the bot
        if any(phrase in text_lower for phrase in [
            "your name", "who are you", "what are you", "what can you do",
            "help me", "how do you work", "introduce yourself", "about you"
        ]):
            return "I'm MusicBuddy! I can play music based on your mood, control playback, answer questions about songs, and remember your preferences. Try 'play some chill music' or ask 'what song is this?'", {"action": "chat"}

        # Pure chat requests
        if any(phrase in text_lower for phrase in [
            "chat with me", "talk to me", "let's talk", "let's chat",
            "just chat", "wanna chat", "can we talk"
        ]):
            return "Sure, I'm here! What's on your mind? We can talk about music, your day, or I can play something for you.", {"action": "chat"}

        # ═══════════════════════════════════════════════════════════════════════
        # FEELINGS (Just acknowledge, don't search unless they ask for music)
        # ═══════════════════════════════════════════════════════════════════════
        feeling_words = ["feeling", "i am", "i'm", "today i", "my mood"]
        mood_words = ["cool", "good", "great", "awesome", "fine", "okay", "ok", "happy", "excited"]
        negative_moods = ["sad", "low", "down", "depressed", "lonely", "tired", "stressed"]

        if any(f in text_lower for f in feeling_words):
            # Check if they're also asking for music
            wants_music = any(w in text_lower for w in ["play", "music", "song", "listen", "put on"])

            if any(m in text_lower for m in mood_words) and not wants_music:
                return "That's great to hear! Glad you're feeling good. Want me to play some music to match your vibe?", {"action": "chat"}
            elif any(m in text_lower for m in negative_moods) and not wants_music:
                return "I hear you. Sometimes we all feel that way. Would you like me to play some comforting music?", {"action": "chat"}
            elif not wants_music:
                return "Thanks for sharing! Would you like me to play some music for you?", {"action": "chat"}

        # ═══════════════════════════════════════════════════════════════════════
        # STATS REQUEST
        # ═══════════════════════════════════════════════════════════════════════
        if text_lower in ["stats", "statistics", "my stats", "listening stats", "history", "my history"]:
            return "Here are your listening stats!", {"action": "stats"}

        # ═══════════════════════════════════════════════════════════════════════
        # INFO ABOUT CURRENT TRACK (Use context, don't search!)
        # ═══════════════════════════════════════════════════════════════════════
        info_phrases = [
            "what song", "what's playing", "current song", "what is this",
            "tell me about this", "info about this", "about this song",
            "who sings", "who is the artist", "what artist", "who's singing",
            "information about", "details about", "about the song",
            "about the artist", "tell me more", "more info", "song info",
            "artist info", "what's this song", "which song", "name of this"
        ]
        if any(phrase in text_lower for phrase in info_phrases):
            if self._current_track:
                name = self._current_track.get('name', 'Unknown')
                artist = self._current_track.get('artist', 'Unknown')
                album = self._current_track.get('album', '')
                response = f"This is \"{name}\" by {artist}."
                if album:
                    response += f" It's from the album \"{album}\"."
                response += " Want to know more, or shall I play something similar?"
                return response, {"action": "info"}
            return "Nothing is playing right now. Want me to play something for you?", {"action": "info"}

        # ═══════════════════════════════════════════════════════════════════════
        # PLAYBACK CONTROLS
        # ═══════════════════════════════════════════════════════════════════════
        if any(word in text_lower for word in ["pause", "stop"]) and "play" not in text_lower:
            return "Paused!", {"action": "pause"}

        if any(word in text_lower for word in ["next", "skip"]):
            return "Skipping to next track!", {"action": "next"}

        if any(word in text_lower for word in ["previous", "back", "go back"]):
            return "Going back to previous track!", {"action": "previous"}

        if text_lower in ["resume", "continue", "unpause"]:
            return "Resuming playback!", {"action": "play"}

        if "shuffle" in text_lower:
            return "Shuffle mode on!", {"action": "shuffle"}

        # ═══════════════════════════════════════════════════════════════════════
        # EXPLICIT MUSIC/PODCAST SEARCH (Only when user clearly wants to play)
        # ═══════════════════════════════════════════════════════════════════════
        play_words = ["play", "put on", "queue", "listen to", "find me", "i want to hear"]
        if any(word in text_lower for word in play_words):
            # Podcast search
            if "podcast" in text_lower:
                query = text_lower
                for word in play_words:
                    query = query.replace(word, "")
                query = query.strip()
                if "intellectual" in text_lower or "educational" in text_lower:
                    return "Finding an intellectual podcast for you!", {"action": "search", "query": "intellectual discussion podcast TED educational"}
                return "Finding podcasts for you!", {"action": "search", "query": f"{query} podcast discussion"}

            # Music search - extract mood/language
            moods = ["sad", "happy", "calm", "energetic", "chill", "romantic", "focus", "melancholy", "upbeat", "relaxing"]
            languages = ["telugu", "hindi", "kannada", "tamil", "english", "korean", "spanish", "punjabi", "japanese", "arabic"]

            found_mood = next((m for m in moods if m in text_lower), None)
            found_lang = next((l for l in languages if l in text_lower), None)

            if found_mood or found_lang:
                query_parts = []
                if found_lang:
                    query_parts.append(found_lang)
                if found_mood:
                    query_parts.append(found_mood)
                query_parts.append("songs music")
                return f"Playing {' '.join(query_parts[:-1])} music!", {"action": "search", "query": " ".join(query_parts)}

            # Generic play request
            clean_query = text_lower
            for word in play_words:
                clean_query = clean_query.replace(word, "")
            clean_query = clean_query.replace("some", "").replace("me", "").strip()
            if clean_query:
                return f"Finding '{clean_query}' for you!", {"action": "search", "query": clean_query}
            return "What would you like me to play? Try: 'play sad Telugu songs' or 'play upbeat workout music'", {"action": "chat"}

        # Recommend/surprise
        if any(word in text_lower for word in ["recommend", "suggest", "surprise me"]):
            return "Let me surprise you with something good!", {"action": "search", "query": "popular trending music hits"}

        # ═══════════════════════════════════════════════════════════════════════
        # DEFAULT: Just chat, don't assume music search
        # ═══════════════════════════════════════════════════════════════════════
        return "I'm here to help with music! You can say 'play some chill music', ask 'what song is this?', or just chat with me.", {"action": "chat"}

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
