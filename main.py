#!/usr/bin/env python3
"""
Music AI Agent - CLI Interface

A conversational AI agent that controls Spotify or YouTube Music
based on mood and preferences.
"""

import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

from config import load_config, Platform
from tools.base import MusicClient
from agent.orchestrator import Agent


console = Console()


def print_welcome(platform: str):
    """Print welcome message."""
    welcome_text = f"""
[bold cyan]Music AI Agent[/bold cyan] - {platform}
Control your music with natural language.

[dim]Examples:[/dim]
  - "Play some sad Telugu songs"
  - "I need energetic workout music"
  - "Calm lo-fi for studying"
  - "Next" / "Pause" / "What's playing?"

[dim]Commands:[/dim]
  - "stats" - View your listening memory
  - "switch" - Switch music platform
  - "help" - Show this message
  - "quit" - Exit
"""
    console.print(Panel(welcome_text, border_style="cyan"))


def print_response(response):
    """Print agent response with formatting."""
    style = "green" if response.success else "red"
    console.print(f"\n[{style}]->[/{style}] {response.message}")

    if response.tracks_played and len(response.tracks_played) > 1:
        console.print("\n[dim]Queue:[/dim]")
        for i, track in enumerate(response.tracks_played[:5], 1):
            console.print(f"  [dim]{i}.[/dim] {track.name} - {track.artist}")
        if len(response.tracks_played) > 5:
            console.print(f"  [dim]... and {len(response.tracks_played) - 5} more[/dim]")


def print_stats(agent: Agent):
    """Print memory statistics."""
    stats = agent.get_memory_stats()

    table = Table(title="Listening Memory", border_style="cyan")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Total Interactions", str(stats["total_entries"]))
    table.add_row("Unique Tracks", str(stats["unique_tracks"]))

    if stats["moods"]:
        mood_str = ", ".join(f"{k}: {v}" for k, v in sorted(stats["moods"].items(), key=lambda x: -x[1])[:5])
        table.add_row("Top Moods", mood_str)

    if stats["languages"]:
        lang_str = ", ".join(f"{k}: {v}" for k, v in sorted(stats["languages"].items(), key=lambda x: -x[1]))
        table.add_row("Languages", lang_str)

    if stats["actions"]:
        action_str = ", ".join(f"{k}: {v}" for k, v in stats["actions"].items())
        table.add_row("Actions", action_str)

    console.print()
    console.print(table)


def select_platform() -> Platform:
    """Let user select music platform."""
    console.print("\n[bold cyan]Select Music Platform:[/bold cyan]")
    console.print("  [1] YouTube Music (no API key needed)")
    console.print("  [2] Spotify (requires developer credentials)")

    choice = Prompt.ask("\nChoice", choices=["1", "2"], default="1")

    if choice == "2":
        return Platform.SPOTIFY
    return Platform.YOUTUBE_MUSIC


def init_youtube_music(config) -> MusicClient:
    """Initialize YouTube Music client."""
    from tools.youtube_music import YouTubeMusicClient, YouTubeMusicConfig, setup_youtube_auth

    auth_file = config.youtube_music.auth_file

    # Check if auth exists
    if not auth_file or not auth_file.exists():
        console.print("\n[yellow]YouTube Music authentication required.[/yellow]")
        console.print("[dim]This is a one-time setup to access your library.[/dim]\n")

        if Confirm.ask("Set up authentication now?", default=True):
            auth_file = config.data_dir / "ytmusic_auth.json"
            if setup_youtube_auth(auth_file):
                config.youtube_music.auth_file = auth_file
            else:
                console.print("[yellow]Continuing without authentication (limited features).[/yellow]")
                auth_file = None
        else:
            console.print("[yellow]Continuing without authentication.[/yellow]")
            console.print("[dim]You can still search and play music, but library features won't work.[/dim]")
            auth_file = None

    yt_config = YouTubeMusicConfig(
        auth_file=auth_file,
        auth_type=config.youtube_music.auth_type,
    )

    return YouTubeMusicClient(yt_config)


def init_spotify(config) -> MusicClient:
    """Initialize Spotify client."""
    from tools.spotify import SpotifyClient

    if not config.spotify.client_id or not config.spotify.client_secret:
        console.print(Panel(
            "[red]Missing Spotify credentials![/red]\n\n"
            "1. Go to https://developer.spotify.com/dashboard\n"
            "2. Create an app\n"
            "3. Copy the Client ID and Client Secret\n"
            "4. Add to .env file:\n"
            "   SPOTIFY_CLIENT_ID=your_id\n"
            "   SPOTIFY_CLIENT_SECRET=your_secret\n\n"
            "[yellow]Note: Spotify may not be accepting new apps currently.[/yellow]",
            title="Setup Required",
            border_style="red",
        ))
        raise SystemExit(1)

    return SpotifyClient(config.spotify, cache_path=config.data_dir / ".spotify_cache")


def init_client(config, platform: Platform) -> MusicClient:
    """Initialize the appropriate music client."""
    if platform == Platform.YOUTUBE_MUSIC:
        console.print("[dim]Connecting to YouTube Music...[/dim]")
        client = init_youtube_music(config)
        if hasattr(client, 'is_authenticated') and client.is_authenticated():
            console.print("[green]Connected to YouTube Music (authenticated)[/green]")
        else:
            console.print("[yellow]Connected to YouTube Music (limited mode)[/yellow]")
        return client
    else:
        console.print("[dim]Connecting to Spotify...[/dim]")
        client = init_spotify(config)
        user = client.user_id
        console.print(f"[green]Connected as {user}[/green]")
        return client


def main():
    """Main CLI loop."""
    console.print()
    console.print("[bold]Music AI Agent[/bold]")
    console.print("[dim]A conversational music controller[/dim]\n")

    # Load config
    try:
        config = load_config()
    except Exception as e:
        console.print(f"[red]Error loading config: {e}[/red]")
        sys.exit(1)

    # Select platform
    # Check if platform is set in env, otherwise ask
    platform = config.platform

    # If default (youtube_music) and no auth file exists, prompt for selection
    if platform == Platform.YOUTUBE_MUSIC:
        auth_file = config.youtube_music.auth_file
        if not auth_file or not auth_file.exists():
            # First run - let user choose
            if not config.spotify.client_id:  # No Spotify credentials either
                console.print("[dim]Using YouTube Music (default)[/dim]")
            else:
                platform = select_platform()

    # Initialize client
    try:
        client = init_client(config, platform)
    except Exception as e:
        console.print(f"[red]Failed to connect: {e}[/red]")
        if config.debug:
            console.print_exception()
        sys.exit(1)

    # Initialize agent
    agent = Agent(config, client)

    platform_name = "YouTube Music" if platform == Platform.YOUTUBE_MUSIC else "Spotify"
    print_welcome(platform_name)

    # Main loop
    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]").strip()

            if not user_input:
                continue

            # Special commands
            cmd = user_input.lower()

            if cmd in ("quit", "exit", "q"):
                console.print("[dim]Goodbye![/dim]")
                break

            if cmd == "stats":
                print_stats(agent)
                continue

            if cmd == "help":
                print_welcome(platform_name)
                continue

            if cmd == "switch":
                console.print("\n[yellow]Switching platform...[/yellow]")
                new_platform = select_platform()
                if new_platform != platform:
                    try:
                        client = init_client(config, new_platform)
                        agent = Agent(config, client)
                        platform = new_platform
                        platform_name = "YouTube Music" if platform == Platform.YOUTUBE_MUSIC else "Spotify"
                        console.print(f"[green]Switched to {platform_name}[/green]")
                    except Exception as e:
                        console.print(f"[red]Failed to switch: {e}[/red]")
                continue

            if cmd == "devices":
                devices = client.get_devices()
                if devices:
                    console.print(f"\n[cyan]Available {platform_name} devices:[/cyan]")
                    for d in devices:
                        active = " [green](active)[/green]" if d.get("is_active") else ""
                        console.print(f"  - {d.get('name', 'Unknown')} ({d.get('type', 'device')}){active}")
                else:
                    if platform == Platform.YOUTUBE_MUSIC:
                        console.print("[dim]YouTube Music plays in your browser.[/dim]")
                    else:
                        console.print(f"[yellow]No devices found. Open {platform_name} somewhere.[/yellow]")
                continue

            # Process through agent
            response = agent.run(user_input)
            print_response(response)

        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye![/dim]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            if config.debug:
                console.print_exception()


if __name__ == "__main__":
    main()
