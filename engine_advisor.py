#!/usr/bin/env python3
"""
The Engine — Advisor Strategy Runtime
Team 2950 — The Devastators

Wraps the Anthropic Advisor Strategy (Haiku executor + Opus advisor) around
ALL Engine subsystems: Scout, Oracle, Blueprint, Pre-event, and Pick Board.

The executor (Haiku) handles routine operations — data fetching, formatting,
recording picks, running calculations. When a strategic decision is needed,
it escalates to the advisor (Opus) automatically.

This is the "brain" that students interact with at competition or during
development. Cheap to run, smart when it matters.

Usage:
  # Interactive mode (chat)
  python3 engine_advisor.py

  # Single query
  python3 engine_advisor.py "Who should 2881 pick at 2026txbel?"

  # Use Sonnet as executor instead of Haiku (more capable, higher cost)
  python3 engine_advisor.py --executor sonnet "Run pre-event report for 2026txbel"

Environment:
  ANTHROPIC_API_KEY  — required (Anthropic API key)
"""

import json
import os
import sys
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("Run: pip3 install anthropic")
    sys.exit(1)


# ─── Configuration ───

MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

DEFAULT_EXECUTOR = "haiku"
DEFAULT_ADVISOR = "opus"
MAX_ADVISOR_USES = 5  # per request, keeps cost bounded

ENGINE_DIR = Path(__file__).parent
SCOUT_DIR = ENGINE_DIR / "scout"
BLUEPRINT_DIR = ENGINE_DIR / "blueprint"


# ─── System Prompt ───

SYSTEM_PROMPT = """You are The Engine — an AI assistant for FRC Team 2950 The Devastators.

You have access to an `advisor` tool backed by a stronger model (Opus). It takes NO parameters — when you call advisor(), your entire conversation is forwarded automatically.

## When to call advisor:
- Before making any strategic recommendation (alliance picks, match strategy, mechanism choices)
- Before interpreting complex data (EPA trends, complementarity analysis, playoff simulations)
- When the user asks "who should we pick" or "what's the best strategy"
- When generating match strategy briefs (opponent counters, defense decisions, auto coordination)
- When synthesizing EYE scouting data with EPA for pick recommendations
- When stuck or uncertain about the right approach
- When the task is complete, to verify your answer

## When NOT to call advisor:
- Simple data lookups ("what's team 2950's EPA?")
- Recording picks or updating state ("A1 picked 148")
- Displaying boards or listings
- Cache management or formatting

## Available Tools (via shell):
You can run Python scripts from The Engine's toolkit:

### Scout — Scouting & Match Intelligence (scout/)
- `python3 scout/the_scout.py report <event_key> --team N` — Pre-event scouting report
- `python3 scout/the_scout.py picks <event_key> --team N` — Alliance pick recommendations
- `python3 scout/the_scout.py lookup <team_number>` — Team EPA lookup
- `python3 scout/the_scout.py compare <event_key> --teams 2950,3005,6800` — Compare teams

### Pick Board — Live Alliance Draft (scout/)
- `python3 scout/pick_board.py setup <event_key> --team N --seed N [--captains ...]` — Initialize draft
- `python3 scout/pick_board.py pick <alliance#> <team#>` — Record a pick
- `python3 scout/pick_board.py board` — Show full pick board
- `python3 scout/pick_board.py rec` — Get pick recommendation
- `python3 scout/pick_board.py undo` — Undo last pick
- `python3 scout/pick_board.py alliances` — Show current alliances
- `python3 scout/pick_board.py sim --sims N` — Monte Carlo playoff simulation
- `python3 scout/pick_board.py dnp <team#>` — Toggle Do Not Pick (excludes from rec)
- `python3 scout/pick_board.py dp` — Project district ranking points from playoffs
- `python3 scout/pick_board.py predict` — Predict captain picks + backfill (with decline modeling)

### Oracle — Game Prediction Engine (blueprint/)
- `python3 blueprint/oracle.py predict <game_rules.json>` — Predict optimal robot design
- `python3 blueprint/oracle.py validate` — Validate against historical games
- `python3 blueprint/oracle.py pipeline <game_rules.json>` — Full prediction → mechanism → BOM

### Trajectory — Multi-Event EPA Tracking (scout/)
- `python3 scout/trajectory.py team <team#> <year>` — EPA trajectory for a team across events
- `python3 scout/trajectory.py compare <team1,team2,...> <year>` — Compare EPA trajectories
- `python3 scout/trajectory.py event <event_key>` — All teams at event with trajectory context
- `python3 scout/trajectory.py movers <district_key>` — Biggest risers/fallers in district

### The EYE — Vision Match Scouting (eye/)
- `python3 eye/the_eye.py analyze <youtube_url> [--focus 2950] [--tier key] [--backend haiku]` — Full analysis
- `python3 eye/the_eye.py frames <youtube_url> [--fps 5]` — Extract frames only (no API)
- `python3 eye/the_eye.py ocr <frames_dir>` — OCR-only analysis (free)
- `python3 eye/the_eye.py scout <frames_dir> [--tier key] [--backend haiku]` — Vision analysis on frames
- Tiers: key (12 frames, cheapest), scored (~50 score-change), all (every frame)
- Backends: haiku (default), sonnet, opus, gemma*, qwen*, moondream*, yolo* (* = coming soon)

### Stand Scout — Human Scouting Input (scout/)
- `python3 scout/stand_scout.py add <team> <tags...> [note:"text"]` — Record observation
- `python3 scout/stand_scout.py team <team#>` — Show all observations for a team
- `python3 scout/stand_scout.py summary [event_key]` — Coverage summary
- Tags: auto:scored, auto:moved, fast, moderate, slow, fuel, tower, climbed, barge
-        played-defense, received-defense, intake-jam, disabled, elite, solid, weak, carried

### EYE Bridge — Wire Scouting Data into Pick Board (eye/)
- `python3 eye/eye_bridge.py load [event_key]` — Load EYE + stand scout reports into pick board
- `python3 eye/eye_bridge.py scores` — Show blended scores for all scouted teams
- `python3 eye/eye_bridge.py team <team#>` — Detailed scouting data for a team
- After loading, pick_board.py rec uses scouting data in scoring (10% weight)
- Stand scout observations weighted 1.5x per match vs EYE (human tracked one robot)

### Match Strategy — Pre-Match Game Plans (scout/)
- `python3 scout/match_strategy.py match <event_key> <match_key> --team N` — Strategy for specific match
- `python3 scout/match_strategy.py next <event_key> --team N` — Strategy for next upcoming match
- `python3 scout/match_strategy.py opponent <event_key> --teams T1,T2,T3` — Quick opponent report
- `python3 scout/match_strategy.py synergy <event_key> --alliance T1,T2,T3` — Alliance synergy analysis

### Backtester — Algorithm Validation (scout/)
- `python3 scout/backtester.py <event_key>` — Backtest pick recs against actual picks at one event
- `python3 scout/backtester.py <district_key>` — Backtest across all events in a district

### Data Clients (scout/)
- `python3 -c "from scout.statbotics_client import ...; ..."` — Statbotics EPA data
- `python3 -c "from scout.tba_client import ...; ..."` — TBA match data, alliances, rankings

## Key context:
- FRC snake draft: R1 picks 1→8, R2 picks 8→1
- QF bracket: 1v8, 2v7, 3v6, 4v5 (best of 3)
- EPA = Expected Points Added (Statbotics). Floor = EPA - 1.5×SD. Ceiling = EPA + 1.5×SD.
- District ranking points come from individual match wins in playoffs, not just series wins
- Rankings determine captain order, not EPA
- TBA API key is configured in scout/.tba_key
- EYE + stand scout data enriches recommendations: reliability, driver skill, defense resistance
- Match strategy integrates EPA + EYE + stand scout + opponent analysis into actionable game plans
- Discord bot (antenna/bot.py) has all scouting commands: !scout, !scouted, !strategy, !rec, !pick, !board
- !event sets active event per channel, !matchnow tracks current match for auto-tagging

## Style:
- Be direct and concise
- Lead with the recommendation, then the reasoning
- Use tables for comparisons
- When showing picks, always show EPA, Floor, and what the projected R2 would be
"""


# ─── Advisor Client ───


def create_client():
    """Create Anthropic client."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        key_file = ENGINE_DIR / ".anthropic_key"
        if key_file.exists():
            api_key = key_file.read_text().strip()
    if not api_key:
        print("  ERROR: ANTHROPIC_API_KEY not set.")
        print("  export ANTHROPIC_API_KEY=<key>")
        print("  or put it in TheEngine/.anthropic_key")
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key)


def run_with_advisor(client, messages, executor_model="haiku",
                     advisor_model="opus", max_advisor_uses=MAX_ADVISOR_USES,
                     max_tokens=4096):
    """
    Run a request using the Advisor Strategy.

    Executor (Haiku/Sonnet) handles the request, escalating to
    Advisor (Opus) for strategic decisions.
    """
    executor_id = MODELS.get(executor_model, executor_model)
    advisor_id = MODELS.get(advisor_model, advisor_model)

    tools = [
        {
            "type": "advisor_20260301",
            "name": "advisor",
            "model": advisor_id,
            "max_uses": max_advisor_uses,
        }
    ]

    response = client.beta.messages.create(
        model=executor_id,
        max_tokens=max_tokens,
        betas=["advisor-tool-2026-03-01"],
        system=SYSTEM_PROMPT,
        tools=tools,
        messages=messages,
    )

    return response


def run_without_advisor(client, messages, model="sonnet", max_tokens=4096):
    """Fallback: run without advisor (if beta not available)."""
    model_id = MODELS.get(model, model)
    response = client.messages.create(
        model=model_id,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return response


def extract_text(response) -> str:
    """Extract text content from a response."""
    parts = []
    for block in response.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts)


def extract_usage(response) -> dict:
    """Extract token usage from response."""
    usage = response.usage
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }


# ─── Interactive Mode ───


def interactive(executor_model="haiku", advisor_model="opus"):
    """Interactive chat with The Engine."""
    client = create_client()
    messages = []
    use_advisor = True

    print(f"\n  THE ENGINE — Advisor Strategy Runtime")
    print(f"  Team 2950 The Devastators")
    print(f"  Executor: {executor_model} | Advisor: {advisor_model}")
    print(f"  Type 'quit' to exit, 'cost' to see token usage")
    print(f"  {'─' * 50}\n")

    total_input = 0
    total_output = 0
    advisor_calls = 0

    while True:
        try:
            user_input = input("  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if user_input.lower() == "cost":
            print(f"\n  Token usage: {total_input:,} in / {total_output:,} out")
            print(f"  Advisor calls: {advisor_calls}\n")
            continue

        messages.append({"role": "user", "content": user_input})

        try:
            if use_advisor:
                response = run_with_advisor(
                    client, messages,
                    executor_model=executor_model,
                    advisor_model=advisor_model,
                )
            else:
                response = run_without_advisor(client, messages, model=executor_model)

            text = extract_text(response)
            usage = extract_usage(response)
            total_input += usage["input_tokens"]
            total_output += usage["output_tokens"]

            # Count advisor calls
            for block in response.content:
                if hasattr(block, "type") and block.type == "server_tool_use":
                    advisor_calls += 1

            # Add assistant response to history
            # For multi-turn, we need to pass back the full content blocks
            messages.append({"role": "assistant", "content": response.content})

            print(f"\n  Engine: {text}\n")

        except anthropic.BadRequestError as e:
            if "advisor" in str(e).lower():
                print(f"\n  Advisor beta not available. Falling back to {executor_model} only.")
                use_advisor = False
                # Retry without advisor
                response = run_without_advisor(client, messages, model=executor_model)
                text = extract_text(response)
                messages.append({"role": "assistant", "content": response.content})
                print(f"\n  Engine: {text}\n")
            else:
                print(f"\n  API Error: {e}\n")
                messages.pop()  # Remove failed user message

        except Exception as e:
            print(f"\n  Error: {e}\n")
            messages.pop()


# ─── Single Query Mode ───


def single_query(query, executor_model="haiku", advisor_model="opus"):
    """Run a single query and print the result."""
    client = create_client()
    messages = [{"role": "user", "content": query}]

    try:
        response = run_with_advisor(
            client, messages,
            executor_model=executor_model,
            advisor_model=advisor_model,
        )
    except anthropic.BadRequestError:
        print("  (Advisor beta not available, using executor only)")
        response = run_without_advisor(client, messages, model=executor_model)

    text = extract_text(response)
    usage = extract_usage(response)

    print(text)
    print(f"\n  [{usage['input_tokens']:,} in / {usage['output_tokens']:,} out]")


# ─── Programmatic API ───


class EngineAdvisor:
    """
    Programmatic interface for other Engine subsystems to use the
    advisor pattern.

    Usage:
        advisor = EngineAdvisor()
        result = advisor.ask("Given these EPAs, who should alliance 3 pick?")
        result = advisor.ask("Analyze this game manual section", executor="sonnet")
    """

    def __init__(self, executor="haiku", advisor="opus"):
        self.client = create_client()
        self.executor = executor
        self.advisor = advisor
        self.messages = []

    def ask(self, prompt: str, executor=None, max_advisor_uses=None) -> str:
        """Send a query, get a response. Maintains conversation history."""
        self.messages.append({"role": "user", "content": prompt})

        response = run_with_advisor(
            self.client,
            self.messages,
            executor_model=executor or self.executor,
            advisor_model=self.advisor,
            max_advisor_uses=max_advisor_uses or MAX_ADVISOR_USES,
        )

        text = extract_text(response)
        self.messages.append({"role": "assistant", "content": response.content})
        return text

    def ask_once(self, prompt: str, executor=None) -> str:
        """Stateless single query (no conversation history)."""
        messages = [{"role": "user", "content": prompt}]
        response = run_with_advisor(
            self.client, messages,
            executor_model=executor or self.executor,
            advisor_model=self.advisor,
        )
        return extract_text(response)

    def reset(self):
        """Clear conversation history."""
        self.messages = []


# ─── CLI ───


def main():
    args = sys.argv[1:]
    executor = DEFAULT_EXECUTOR
    advisor = DEFAULT_ADVISOR
    query = None

    i = 0
    while i < len(args):
        if args[i] == "--executor" and i + 1 < len(args):
            executor = args[i + 1]; i += 2
        elif args[i] == "--advisor" and i + 1 < len(args):
            advisor = args[i + 1]; i += 2
        elif args[i] in ("--help", "-h"):
            print(__doc__)
            return
        else:
            # Everything else is the query
            query = " ".join(args[i:])
            break

    if query:
        single_query(query, executor_model=executor, advisor_model=advisor)
    else:
        interactive(executor_model=executor, advisor_model=advisor)


if __name__ == "__main__":
    main()
