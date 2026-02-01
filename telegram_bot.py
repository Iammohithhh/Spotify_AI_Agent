#!/usr/bin/env python3
"""
Telegram Bot Interface for Music AI Agent.

Run with: python telegram_bot.py
"""

import logging
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import load_config, Platform
from tools.youtube_music import YouTubeMusicClient, YouTubeMusicConfig
from tools.spotify import SpotifyClient
from tools.base import MusicClient, Track
from agent.orchestrator import Agent

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Store user sessions
user_sessions: dict[int, dict] = {}


def get_user_agent(user_id: int, config) -> Agent:
    """Get or create agent for a user."""
    if user_id not in user_sessions:
        # Initialize client based on platform
        if config.platform == Platform.YOUTUBE_MUSIC:
            yt_config = YouTubeMusicConfig(
                auth_file=config.youtube_music.auth_file,
                auth_type=config.youtube_music.auth_type,
            )
            client = YouTubeMusicClient(yt_config)
        else:
            client = SpotifyClient(config.spotify, cache_path=config.data_dir / ".spotify_cache")

        agent = Agent(config, client)
        user_sessions[user_id] = {
            "agent": agent,
            "last_tracks": [],
            "current_mood": None,
        }

    return user_sessions[user_id]["agent"]


def get_control_keyboard() -> InlineKeyboardMarkup:
    """Create playback control buttons."""
    keyboard = [
        [
            InlineKeyboardButton("⏮ Prev", callback_data="control_prev"),
            InlineKeyboardButton("⏸ Pause", callback_data="control_pause"),
            InlineKeyboardButton("⏭ Next", callback_data="control_next"),
        ],
        [
            InlineKeyboardButton("🔀 Shuffle", callback_data="control_shuffle"),
            InlineKeyboardButton("🎵 Now Playing", callback_data="control_now"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_mood_keyboard() -> InlineKeyboardMarkup:
    """Create mood selection buttons."""
    keyboard = [
        [
            InlineKeyboardButton("😊 Happy", callback_data="mood_happy"),
            InlineKeyboardButton("😢 Sad", callback_data="mood_sad"),
            InlineKeyboardButton("😌 Calm", callback_data="mood_calm"),
        ],
        [
            InlineKeyboardButton("⚡ Energetic", callback_data="mood_energetic"),
            InlineKeyboardButton("💪 Workout", callback_data="mood_workout"),
            InlineKeyboardButton("📚 Focus", callback_data="mood_focus"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def format_track_list(tracks: list[Track], max_items: int = 5) -> str:
    """Format a list of tracks for display."""
    if not tracks:
        return "_No tracks_"

    lines = []
    for i, track in enumerate(tracks[:max_items], 1):
        lines.append(f"{i}. *{track.name}*\n   _{track.artist}_")

    if len(tracks) > max_items:
        lines.append(f"\n_...and {len(tracks) - max_items} more_")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Command Handlers
# ─────────────────────────────────────────────────────────────────────────────


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    welcome = f"""
🎵 *Welcome to Music AI Agent, {user.first_name}!*

I can play music based on your mood and learn your preferences over time.

*Try saying:*
• "Play some sad Telugu songs"
• "I need energetic workout music"
• "Calm lo-fi for studying"

*Commands:*
/play - Quick mood selection
/stats - View your listening history
/notes - View podcast notes
/help - Show help

Just type naturally and I'll find music for you!
"""
    await update.message.reply_text(
        welcome,
        parse_mode="Markdown",
        reply_markup=get_mood_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = """
🎵 *Music AI Agent - Help*

*Just chat naturally!*
• "Play some sad Telugu songs"
• "What song is this?"
• "Tell me about this artist"
• "Something calm for sleeping"
• "Who sings this?"

*Quick Controls:*
• "next" / "skip" - Next track
• "pause" / "stop" - Pause playback
• "play" / "resume" - Resume

*Commands:*
/play - Quick mood buttons
/now - What's playing now
/stats - Your listening history
/notes - Podcast notes
/help - This message

*Ask me anything about music!*
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def now_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /now command - show current track with details."""
    config = load_config()
    agent = get_user_agent(update.effective_user.id, config)

    state = agent.client.get_playback_state()

    if not state or not state.track:
        await update.message.reply_text(
            "🔇 *Nothing playing right now*\n\nTry asking for some music!",
            parse_mode="Markdown",
            reply_markup=get_mood_keyboard(),
        )
        return

    track = state.track
    status_emoji = "▶️" if state.is_playing else "⏸"

    # Get track URL
    track_url = None
    if agent.client.platform == Platform.YOUTUBE_MUSIC:
        track_url = agent.client.get_web_url(track)

    msg = f"""
{status_emoji} *Now Playing*

🎵 *{track.name}*
👤 {track.artist}
💿 {track.album or 'Unknown Album'}

_Ask me anything about this song or artist!_
"""

    keyboard = [
        [
            InlineKeyboardButton("⏮ Prev", callback_data="control_prev"),
            InlineKeyboardButton("⏸ Pause" if state.is_playing else "▶️ Play", callback_data="control_pause" if state.is_playing else "control_play"),
            InlineKeyboardButton("⏭ Next", callback_data="control_next"),
        ],
    ]

    if track_url:
        keyboard.append([InlineKeyboardButton("🔗 Open in App", url=track_url)])

    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /play command - show mood selection."""
    await update.message.reply_text(
        "🎵 *What's your mood?*\n\nSelect below or just type what you want:",
        parse_mode="Markdown",
        reply_markup=get_mood_keyboard(),
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats command."""
    config = load_config()
    agent = get_user_agent(update.effective_user.id, config)
    stats = agent.get_memory_stats()

    if stats["total_entries"] == 0:
        await update.message.reply_text(
            "📊 *No listening history yet!*\n\nStart playing music to build your profile.",
            parse_mode="Markdown",
        )
        return

    # Format stats
    mood_str = ""
    if stats["moods"]:
        top_moods = sorted(stats["moods"].items(), key=lambda x: -x[1])[:3]
        mood_str = ", ".join(f"{m} ({c})" for m, c in top_moods)

    lang_str = ""
    if stats["languages"]:
        top_langs = sorted(stats["languages"].items(), key=lambda x: -x[1])[:3]
        lang_str = ", ".join(f"{l} ({c})" for l, c in top_langs)

    stats_text = f"""
📊 *Your Listening Stats*

🎵 *Total Plays:* {stats["total_entries"]}
🎼 *Unique Tracks:* {stats["unique_tracks"]}

🎭 *Top Moods:*
{mood_str or "_None yet_"}

🌐 *Languages:*
{lang_str or "_None yet_"}

_Keep listening to improve recommendations!_
"""
    await update.message.reply_text(stats_text, parse_mode="Markdown")


async def notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /notes command - show podcast notes."""
    config = load_config()
    notes_file = config.data_dir / "podcast_notes.json"

    if not notes_file.exists():
        await update.message.reply_text(
            "📝 *No podcast notes yet!*\n\nListen to podcasts and I'll help you take notes.",
            parse_mode="Markdown",
        )
        return

    from tools.notes import NotesManager
    notes_mgr = NotesManager(config.data_dir)
    recent = notes_mgr.get_recent_notes(limit=5)

    if not recent:
        await update.message.reply_text(
            "📝 *No podcast notes yet!*",
            parse_mode="Markdown",
        )
        return

    notes_text = "📝 *Recent Podcast Notes*\n\n"
    for note in recent:
        notes_text += f"*{note.episode_name}*\n"
        notes_text += f"_{note.show_name}_ | {note.listened_percentage}%\n"
        if note.user_notes:
            notes_text += f"Notes: {note.user_notes[:100]}...\n"
        notes_text += "\n"

    await update.message.reply_text(notes_text, parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# Message Handler
# ─────────────────────────────────────────────────────────────────────────────


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle natural language messages."""
    user_id = update.effective_user.id
    text = update.message.text

    config = load_config()
    agent = get_user_agent(user_id, config)

    # Show typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Process through agent
    response = agent.run(text)

    # Store last tracks for reference
    if response.tracks_played:
        user_sessions[user_id]["last_tracks"] = response.tracks_played

    # Different response formats based on action type
    action = response.action_taken

    # Conversational/Info/Stats responses - no playback controls needed
    if action in ["info", "stats", "chat"]:
        emoji_map = {"stats": "📊", "info": "ℹ️", "chat": "💬"}
        emoji = emoji_map.get(action, "💬")
        await update.message.reply_text(
            f"{emoji} {response.message}",
            parse_mode="Markdown",
        )
        return

    # Build response message for music actions
    if response.success:
        msg = f"🎵 {response.message}"

        # Add track list if available
        if response.tracks_played:
            msg += f"\n\n*Queue:*\n{format_track_list(response.tracks_played)}"

        # Add URL for YouTube Music
        if response.open_url:
            msg += f"\n\n[▶️ Open in YouTube Music]({response.open_url})"

        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_control_keyboard(),
            disable_web_page_preview=True,
        )
    else:
        await update.message.reply_text(
            f"❌ {response.message}",
            reply_markup=get_mood_keyboard(),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Callback Query Handler (Button Presses)
# ─────────────────────────────────────────────────────────────────────────────


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button callbacks."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    config = load_config()
    agent = get_user_agent(user_id, config)

    data = query.data

    # Mood selection
    if data.startswith("mood_"):
        mood = data.replace("mood_", "")

        # Map button moods to search queries
        mood_queries = {
            "happy": "happy upbeat songs",
            "sad": "sad emotional songs",
            "calm": "calm relaxing music",
            "energetic": "energetic dance music",
            "workout": "workout gym music",
            "focus": "focus study lo-fi",
        }

        query_text = mood_queries.get(mood, f"{mood} music")
        response = agent.run(query_text)

        if response.tracks_played:
            user_sessions[user_id]["last_tracks"] = response.tracks_played
            user_sessions[user_id]["current_mood"] = mood

        msg = f"🎵 {response.message}"
        if response.tracks_played:
            msg += f"\n\n*Queue:*\n{format_track_list(response.tracks_played)}"
        if response.open_url:
            msg += f"\n\n[▶️ Open in YouTube Music]({response.open_url})"

        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_control_keyboard(),
            disable_web_page_preview=True,
        )

    # Playback controls
    elif data.startswith("control_"):
        action = data.replace("control_", "")

        action_map = {
            "prev": "previous",
            "play": "resume",
            "pause": "pause",
            "next": "next",
            "shuffle": "shuffle",
            "now": "what's playing",
        }

        command = action_map.get(action, action)
        response = agent.run(command)

        await query.edit_message_text(
            f"🎵 {response.message}",
            reply_markup=get_control_keyboard(),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main():
    """Run the Telegram bot."""
    import os

    # Get bot token from environment
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not set in environment")
        print("\nTo create a Telegram bot:")
        print("1. Message @BotFather on Telegram")
        print("2. Send /newbot and follow instructions")
        print("3. Copy the token and add to .env:")
        print("   TELEGRAM_BOT_TOKEN=your_token_here")
        return

    # Load config to initialize
    config = load_config()
    print(f"Starting bot with {config.platform.value} as music platform...")

    # Create application
    app = Application.builder().token(token).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("play", play_command))
    app.add_handler(CommandHandler("now", now_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("notes", notes_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run
    print("Bot is running! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
