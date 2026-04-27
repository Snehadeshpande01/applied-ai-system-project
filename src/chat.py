"""
Conversational music recommender -- RAG entry point with session memory.

Usage:
    python -m src.chat                        # baseline persona
    python -m src.chat --persona casual       # casual friend tone
    python -m src.chat --persona dj           # DJ/producer tone
    python -m src.chat --persona critic       # music critic tone
    python -m src.chat --compare-personas     # run one query through all four personas
    python -m src.chat --no-guide             # disable genre guide (shows RAG enhancement diff)
"""

import argparse
import logging
import sys
from collections import Counter
from dataclasses import dataclass, field
from tabulate import tabulate
from colorama import init as colorama_init, Fore, Style

from src.ai_recommender import get_catalog, parse_user_query, generate_ai_explanation
from src.recommender import recommend_songs

colorama_init(autoreset=True)
logger = logging.getLogger(__name__)

VALID_PERSONAS = ("baseline", "casual", "dj", "critic")

_BANNER = f"""
{Fore.CYAN}{Style.BRIGHT}  ╔══════════════════════════════════════════╗
  ║       AI Music Recommender (RAG)         ║
  ║  Powered by Claude + content-based search║
  ╚══════════════════════════════════════════╝{Style.RESET_ALL}

{Style.DIM}  Tell me what kind of music you're in the mood for.
  Examples:
    "something chill to study to"
    "high-energy songs for the gym"
    "sad indie music for a rainy day"
    "same but more energetic"  (refines previous request)
  Type 'quit' to exit.{Style.RESET_ALL}
"""


# ── Session Memory ────────────────────────────────────────────────────────────

@dataclass
class SessionMemory:
    """Tracks conversation state across turns for context-aware refinements."""
    history: list = field(default_factory=list)   # [{query, prefs, top_song}]
    genre_counts: Counter = field(default_factory=Counter)
    mood_counts: Counter = field(default_factory=Counter)

    def record(self, query: str, prefs: dict, top_song_title: str) -> None:
        self.history.append({"query": query, "prefs": prefs, "top_song": top_song_title})
        self.genre_counts[prefs.get("genre", "")] += 1
        self.mood_counts[prefs.get("mood", "")] += 1

    @property
    def last_prefs(self) -> dict | None:
        return self.history[-1]["prefs"] if self.history else None

    @property
    def top_genre(self) -> str:
        return self.genre_counts.most_common(1)[0][0] if self.genre_counts else ""

    @property
    def top_mood(self) -> str:
        return self.mood_counts.most_common(1)[0][0] if self.mood_counts else ""

    def session_summary(self) -> str:
        if not self.history:
            return ""
        parts = [f"{len(self.history)} quer{'y' if len(self.history) == 1 else 'ies'}"]
        if self.top_genre:
            parts.append(f"genre={self.top_genre}")
        if self.top_mood:
            parts.append(f"mood={self.top_mood}")
        return " · ".join(parts)


# ── Display helpers ───────────────────────────────────────────────────────────

def _score_color(score: float) -> str:
    if score >= 4.0:
        return Fore.GREEN + Style.BRIGHT
    if score >= 2.5:
        return Fore.YELLOW
    return Fore.RED


def _short_reasons(reasons_str: str) -> str:
    parts = []
    if "genre match" in reasons_str:
        parts.append("genre")
    elif "genre family" in reasons_str:
        parts.append("genre~")
    if "mood match" in reasons_str:
        parts.append("mood")
    if "energy" in reasons_str:
        parts.append("energy")
    if "valence fit" in reasons_str:
        parts.append("valence")
    return " + ".join(parts) if parts else reasons_str


def _display_recommendations(recommendations: list) -> None:
    rows = []
    for rank, (song, score, reasons_str) in enumerate(recommendations, 1):
        score_str = f"{_score_color(score)}{score:.2f}{Style.RESET_ALL}"
        rank_str = f"{Fore.CYAN}{rank}{Style.RESET_ALL}" if rank == 1 else str(rank)
        title_str = (
            f"{Style.BRIGHT}{song['title']}{Style.RESET_ALL}"
            if rank == 1
            else song["title"]
        )
        rows.append([
            rank_str, title_str, song["artist"], song["genre"],
            song["mood"], f"{song['energy']:.2f}", score_str,
            _short_reasons(reasons_str),
        ])

    print(tabulate(
        rows,
        headers=[
            f"{Fore.CYAN}#{Style.RESET_ALL}",
            f"{Fore.CYAN}Title{Style.RESET_ALL}",
            f"{Fore.CYAN}Artist{Style.RESET_ALL}",
            f"{Fore.CYAN}Genre{Style.RESET_ALL}",
            f"{Fore.CYAN}Mood{Style.RESET_ALL}",
            f"{Fore.CYAN}Energy{Style.RESET_ALL}",
            f"{Fore.CYAN}Score{Style.RESET_ALL}",
            f"{Fore.CYAN}Why{Style.RESET_ALL}",
        ],
        tablefmt="psql",
    ))
    print()


def _compare_all_personas(
    user_input: str,
    recommendations: list,
    prefs: dict,
    use_guide: bool,
) -> None:
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 56}")
    print("  Persona Comparison -- same songs, four explanation styles")
    print(f"{'=' * 56}{Style.RESET_ALL}")

    for persona in VALID_PERSONAS:
        label_colors = {
            "baseline": Fore.WHITE + Style.BRIGHT,
            "casual":   Fore.MAGENTA + Style.BRIGHT,
            "dj":       Fore.BLUE + Style.BRIGHT,
            "critic":   Fore.YELLOW + Style.BRIGHT,
        }
        color = label_colors.get(persona, Fore.WHITE)
        print(f"\n{color}-- {persona.upper()} --{Style.RESET_ALL}")
        try:
            generate_ai_explanation(
                user_input, recommendations, prefs,
                persona=persona, use_guide=use_guide,
                on_token=lambda t: print(t, end="", flush=True),
            )
            print()
        except Exception as exc:
            print(f"{Fore.RED}  [error: {exc}]{Style.RESET_ALL}")

    print(f"\n{Fore.CYAN}{'=' * 56}{Style.RESET_ALL}\n")
    _display_recommendations(recommendations)


# ── Main chat loop ────────────────────────────────────────────────────────────

def run_chat(persona: str = "baseline", compare: bool = False, use_guide: bool = True) -> None:
    print(_BANNER)
    if persona != "baseline":
        print(f"  {Fore.MAGENTA}Persona: {persona.upper()}{Style.RESET_ALL}\n")
    if not use_guide:
        print(f"  {Fore.YELLOW}Genre guide: DISABLED (RAG enhancement off){Style.RESET_ALL}\n")

    songs = get_catalog()
    session = SessionMemory()

    while True:
        try:
            prompt = f"{Fore.GREEN}You:{Style.RESET_ALL} "
            if session.history:
                summary = session.session_summary()
                prompt = (
                    f"{Style.DIM}[Session: {summary}]{Style.RESET_ALL}\n"
                    f"{Fore.GREEN}You:{Style.RESET_ALL} "
                )
            user_input = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{Style.DIM}Goodbye!{Style.RESET_ALL}")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q", "bye"):
            print(f"{Style.DIM}Goodbye! Happy listening.{Style.RESET_ALL}")
            break

        try:
            print()

            # Step 1: Parse query — inject last turn's prefs for refinement support
            prefs = parse_user_query(user_input, session_prefs=session.last_prefs)
            print(
                f"  {Style.DIM}genre={Fore.CYAN}{prefs['genre']}{Style.RESET_ALL}{Style.DIM}  "
                f"mood={Fore.CYAN}{prefs['mood']}{Style.RESET_ALL}{Style.DIM}  "
                f"energy={Fore.CYAN}{prefs['energy']:.2f}{Style.RESET_ALL}"
            )
            print()

            # Step 2: Retrieve matching songs
            recommendations = recommend_songs(prefs, songs, k=5)

            if not recommendations:
                print(
                    f"{Fore.YELLOW}  Couldn't find matching songs. "
                    f"Try describing the genre or mood differently.{Style.RESET_ALL}\n"
                )
                continue

            # Record this turn in session memory
            session.record(user_input, prefs, recommendations[0][0]['title'])

            if compare:
                _compare_all_personas(user_input, recommendations, prefs, use_guide)
            else:
                print(f"{Fore.GREEN}{Style.BRIGHT}Assistant:{Style.RESET_ALL}")
                generate_ai_explanation(
                    user_input, recommendations, prefs,
                    persona=persona, use_guide=use_guide,
                    on_token=lambda t: print(t, end="", flush=True),
                )
                print("\n")
                _display_recommendations(recommendations)

        except ValueError as exc:
            logger.warning("Input handling error: %s", exc)
            print(f"\n{Fore.YELLOW}  {exc}{Style.RESET_ALL}\n")

        except EnvironmentError as exc:
            logger.critical("Environment error: %s", exc)
            print(f"\n{Fore.RED}Error: {exc}{Style.RESET_ALL}")
            sys.exit(1)

        except Exception as exc:
            logger.error("Unexpected error: %s", exc, exc_info=True)
            print(
                f"\n{Fore.RED}  Something went wrong. "
                f"Please try a different description.{Style.RESET_ALL}\n"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="VibeFinder -- AI Music Recommender")
    parser.add_argument(
        "--persona",
        choices=VALID_PERSONAS,
        default="baseline",
        help="Explanation style: baseline (default), casual, dj, or critic",
    )
    parser.add_argument(
        "--compare-personas",
        action="store_true",
        help="Run each query through all four personas to show style differences",
    )
    parser.add_argument(
        "--no-guide",
        action="store_true",
        help="Disable genre guide retrieval (turns off RAG enhancement)",
    )
    args = parser.parse_args()

    run_chat(
        persona=args.persona,
        compare=args.compare_personas,
        use_guide=not args.no_guide,
    )


if __name__ == "__main__":
    main()
