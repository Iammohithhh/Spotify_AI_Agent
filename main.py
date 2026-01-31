#!/usr/bin/env python3
"""
Spotify AI Agent - CLI Interface

A conversational AI agent that controls Spotify based on mood and preferences.
"""

import sys
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from config import load_config
from tools.spotify import SpotifyClient
from agent.orchestrator import Agent


console = Console()


def print_welcome():
    """Print welcome message."""
    welcome_text = """
[bold cyan]Spotify AI Agent[/bold cyan]
Control your music with natural language.

[dim]Examples:[/dim]
  • "Play some sad Telugu songs"
  • "I need energetic workout music"
  • "Calm lo-fi for studying"
  • "Next" / "Pause" / "What's playing?"
  • "stats" - View your listening memory
  • "quit" - Exit
"""
    console.print(Panel(welcome_text, border_style="cyan"))


def print_response(response):
    """Print agent response with formatting."""
    style = "green" if response.success else "red"
    console.print(f"\n[{style}]→[/{style}] {response.message}")

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


def validate_config(config) -> bool:
    """Validate that required config is present."""
    if not config.spotify.client_id or not config.spotify.client_secret:
        console.print(Panel(
            "[red]Missing Spotify credentials![/red]\n\n"
            "1. Go to https://developer.spotify.com/dashboard\n"
            "2. Create an app\n"
            "3. Copy the Client ID and Client Secret\n"
            "4. Create a .env file (copy from .env.example)\n"
            "5. Add your credentials",
            title="Setup Required",
            border_style="red",
        ))
        return False
    return True


def main():
    """Main CLI loop."""
    console.print()

    # Load config
    try:
        config = load_config()
    except Exception as e:
        console.print(f"[red]Error loading config: {e}[/red]")
        sys.exit(1)

    if not validate_config(config):
        sys.exit(1)

    # Initialize Spotify client
    console.print("[dim]Connecting to Spotify...[/dim]")
    try:
        spotify = SpotifyClient(config.spotify, cache_path=config.data_dir / ".spotify_cache")
        # Test connection by getting user ID
        user = spotify.user_id
        console.print(f"[green]Connected as {user}[/green]\n")
    except Exception as e:
        console.print(f"[red]Failed to connect to Spotify: {e}[/red]")
        console.print("[dim]Make sure your credentials are correct and you've authorized the app.[/dim]")
        sys.exit(1)

    # Initialize agent
    agent = Agent(config, spotify)

    print_welcome()

    # Main loop
    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]").strip()

            if not user_input:
                continue

            # Special commands
            if user_input.lower() in ("quit", "exit", "q"):
                console.print("[dim]Goodbye![/dim]")
                break

            if user_input.lower() == "stats":
                print_stats(agent)
                continue

            if user_input.lower() == "help":
                print_welcome()
                continue

            if user_input.lower() == "devices":
                devices = spotify.get_devices()
                if devices:
                    console.print("\n[cyan]Available devices:[/cyan]")
                    for d in devices:
                        active = " [green](active)[/green]" if d["is_active"] else ""
                        console.print(f"  • {d['name']} ({d['type']}){active}")
                else:
                    console.print("[yellow]No devices found. Open Spotify somewhere.[/yellow]")
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
