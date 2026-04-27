"""
Agentic music recommender using Claude tool_use.

Observable multi-step pipeline:
  Step 1 — User query received; Claude plans which tools to call
  Step 2 — Claude calls get_genre_profile to understand the genre
  Step 3 — Claude calls search_songs to retrieve catalog matches
  Step 4 — Claude synthesizes final recommendation with explanation

This makes the retrieval steps explicit and inspectable, unlike the standard
RAG pipeline where retrieval is hidden inside a single Claude call.

Usage:
    python -m src.agent
"""

import json
import logging
import os
import anthropic
from src.recommender import load_songs, recommend_songs
from src.ai_recommender import get_genre_context, get_catalog

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-7"

# ── Tool definitions (passed to Claude) ──────────────────────────────────────
TOOLS = [
    {
        "name": "get_genre_profile",
        "description": (
            "Get a textual profile of a music genre's characteristics, typical energy range, "
            "use cases, and listener expectations. Call this first to understand what the "
            "user is really asking for before searching the catalog."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "genre": {
                    "type": "string",
                    "description": "Genre name, e.g. 'lofi', 'pop', 'rock', 'r&b', 'metal'",
                }
            },
            "required": ["genre"],
        },
    },
    {
        "name": "search_songs",
        "description": (
            "Search the song catalog and return songs ranked by how well they match "
            "the given preferences. Returns the top 5 results with scores and reasons."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "genre": {"type": "string", "description": "Target genre"},
                "mood": {
                    "type": "string",
                    "description": "One of: happy, chill, sad, intense, focused, romantic",
                },
                "energy": {
                    "type": "number",
                    "description": "Target energy level 0.0 (very calm) to 1.0 (very energetic)",
                },
            },
            "required": ["genre", "mood", "energy"],
        },
    },
]

_AGENT_SYSTEM = """\
You are a music recommendation agent with access to two tools:
  1. get_genre_profile — retrieves genre characteristics from the music knowledge base
  2. search_songs      — queries the song catalog with specific criteria

Always follow this sequence:
  1. Call get_genre_profile to understand the genre the user wants
  2. Call search_songs with refined preferences based on the genre profile
  3. Synthesize a warm, specific explanation of why the results fit the listener

Use both tools before writing your final answer."""


# ── Tool execution functions ──────────────────────────────────────────────────
def _execute_get_genre_profile(genre: str) -> str:
    ctx = get_genre_context(genre)
    if ctx:
        return f"Genre: {genre}\n\n{ctx}"
    return f"No profile found for '{genre}' in knowledge base."


def _execute_search_songs(genre: str, mood: str, energy: float) -> str:
    songs = get_catalog()
    prefs = {"genre": genre, "mood": mood, "energy": energy}
    results = recommend_songs(prefs, songs, k=5)
    if not results:
        return "No songs found matching those criteria."
    lines = []
    for i, (song, score, reasons) in enumerate(results, 1):
        lines.append(
            f"{i}. \"{song['title']}\" by {song['artist']}"
            f" [genre={song['genre']}, mood={song['mood']}, energy={song['energy']:.2f}]"
            f" — score {score:.2f} ({reasons})"
        )
    return "\n".join(lines)


def _dispatch_tool(name: str, tool_input: dict) -> str:
    if name == "get_genre_profile":
        return _execute_get_genre_profile(tool_input["genre"])
    if name == "search_songs":
        return _execute_search_songs(
            tool_input["genre"],
            tool_input["mood"],
            float(tool_input["energy"]),
        )
    return f"Unknown tool: {name}"


# ── Agentic loop ──────────────────────────────────────────────────────────────
def run_agent(user_query: str, verbose: bool = True) -> str:
    """
    Run the multi-step agentic pipeline for a music recommendation query.

    Prints each tool call and result as it happens (observable intermediate steps).
    Returns the final text response from Claude.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)

    messages = [{"role": "user", "content": user_query}]
    step = 1

    if verbose:
        print(f"\n[Step {step}] User query: {user_query!r}")

    while True:
        step += 1
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=_AGENT_SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        # Append assistant turn to history
        messages.append({"role": "assistant", "content": response.content})

        # If no tool calls, Claude is done — extract final text
        if response.stop_reason == "end_turn":
            final_text = next(
                (block.text for block in response.content if block.type == "text"), ""
            )
            if verbose:
                print(f"\n[Step {step}] Final recommendation:\n{final_text}")
            return final_text

        # Process tool calls and collect results
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            if verbose:
                print(f"\n[Step {step}] Tool call: {block.name}({json.dumps(block.input)})")

            result_text = _dispatch_tool(block.name, block.input)

            if verbose:
                # Indent result for readability
                indented = "\n".join(f"  {line}" for line in result_text.splitlines())
                print(f"          Result:\n{indented}")

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                }
            )
            step += 1

        # Feed tool results back to Claude
        messages.append({"role": "user", "content": tool_results})


# ── Interactive chat loop ─────────────────────────────────────────────────────
def run_agent_chat() -> None:
    _BANNER = """\
+--------------------------------------------------+
|      VibeFinder -- Agentic Mode (tool_use)       |
|  Watch Claude plan, retrieve, then explain       |
+--------------------------------------------------+
Each query shows the intermediate tool calls before the final answer.
Type 'quit' to exit.
"""
    print(_BANNER)

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q", "bye"):
            print("Goodbye! Happy listening.")
            break

        try:
            print("\n" + "-" * 56)
            run_agent(user_input, verbose=True)
            print("-" * 56 + "\n")
        except EnvironmentError as exc:
            print(f"\nError: {exc}")
            break
        except anthropic.APIError as exc:
            print(f"\nAPI error: {exc}\nPlease try again.")


if __name__ == "__main__":
    run_agent_chat()
