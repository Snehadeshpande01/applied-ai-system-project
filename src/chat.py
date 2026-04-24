"""
Conversational music recommender — RAG entry point.

Usage:
    python -m src.chat

Flow (per user turn):
  1. Claude extracts genre/mood/energy from natural language (parse_user_query)
  2. Existing rule-based scorer retrieves top-5 songs            (recommend_songs)
  3. Claude explains results using retrieved songs as context    (generate_ai_explanation)
"""

import logging
import sys
from src.ai_recommender import get_catalog, parse_user_query, generate_ai_explanation
from src.recommender import recommend_songs

logger = logging.getLogger(__name__)

_BANNER = """\
╔══════════════════════════════════════════╗
║       AI Music Recommender (RAG)         ║
║  Powered by Claude + content-based search║
╚══════════════════════════════════════════╝
Tell me what kind of music you're in the mood for.
Examples:
  "something chill to study to"
  "high-energy songs for the gym"
  "sad indie music for a rainy day"
Type 'quit' to exit.
"""


def run_chat() -> None:
    print(_BANNER)
    songs = get_catalog()

    while True:
        # ── Get user input ────────────────────────────────────────────────────
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

        # ── RAG pipeline ──────────────────────────────────────────────────────
        try:
            # Step 1: Natural language → structured preferences (Claude)
            prefs = parse_user_query(user_input)

            # Step 2: Retrieve matching songs with existing scorer
            recommendations = recommend_songs(prefs, songs, k=5)

            if not recommendations:
                print(
                    "\nAssistant: I couldn't find matching songs for that. "
                    "Try describing the genre or mood differently.\n"
                )
                continue

            # Step 3: Claude explains results using retrieved songs as context
            explanation = generate_ai_explanation(user_input, recommendations, prefs)

            # ── Display ───────────────────────────────────────────────────────
            print(f"\nAssistant: {explanation}\n")
            print("Ranked picks:")
            for rank, (song, score, _) in enumerate(recommendations, 1):
                print(
                    f"  {rank}. {song['title']} by {song['artist']}"
                    f"  [{song['genre']} / {song['mood']} / energy {song['energy']:.2f}]"
                    f"  score: {score:.2f}"
                )
            print()

        except ValueError as exc:
            # Guardrail: bad input / JSON parse failure
            logger.warning("Input handling error: %s", exc)
            print(f"\nAssistant: {exc}\n")

        except EnvironmentError as exc:
            # Missing API key — unrecoverable, exit cleanly
            logger.critical("Environment error: %s", exc)
            print(f"\nError: {exc}")
            sys.exit(1)

        except Exception as exc:  # noqa: BLE001
            # Unexpected errors — log and continue
            logger.error("Unexpected error: %s", exc, exc_info=True)
            print(
                "\nAssistant: Something went wrong on my end. "
                "Please try a different description.\n"
            )


if __name__ == "__main__":
    run_chat()
