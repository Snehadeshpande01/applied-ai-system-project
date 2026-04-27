"""
eval.py - Evaluation harness for VibeFinder

Runs a fixed set of predefined test cases and prints a pass/fail summary
with confidence ratings and NDCG@5 scores.

Usage:
    python eval.py               # offline scorer tests only (no API key needed)
    python eval.py --online      # offline + online AI parser tests
    python eval.py --rag-compare # show RAG quality improvement (with vs without genre guide)
"""

import argparse
import math
import sys
from dataclasses import dataclass
from colorama import init as colorama_init, Fore, Style

from src.recommender import load_songs, recommend_songs

colorama_init(autoreset=True)


# ── Test case definitions ─────────────────────────────────────────────────────

@dataclass
class ScorerTest:
    label: str
    prefs: dict
    expected_top_song: str
    expected_in_top3: list
    min_top_score: float
    # Ground-truth relevance labels: song_title → relevance (3=perfect, 2=good, 1=ok, 0=poor)
    relevance: dict


@dataclass
class ParserTest:
    label: str
    query: str
    expected_genres: list
    expected_moods: list
    energy_min: float
    energy_max: float


SCORER_TESTS = [
    ScorerTest(
        label="Chill Lofi - perfect catalog match",
        prefs={"genre": "lofi", "mood": "chill", "energy": 0.35},
        expected_top_song="Library Rain",
        expected_in_top3=["Library Rain", "Midnight Coding"],
        min_top_score=4.0,
        relevance={
            "Library Rain": 3, "Rainy Window": 3, "Tea & Vinyl": 3,
            "Coastal Rain": 2, "Midnight Coding": 2, "Deep Work": 2,
            "Focus Flow": 2, "Spacewalk Thoughts": 1, "Blue Note Evening": 1,
            "Aurora Float": 1,
        },
    ),
    ScorerTest(
        label="High-Energy Pop - gym workout",
        prefs={"genre": "pop", "mood": "happy", "energy": 0.80},
        expected_top_song="Sunrise City",
        expected_in_top3=["Sunrise City", "Dance All Night"],
        min_top_score=4.0,
        relevance={
            "Sunrise City": 3, "Dance All Night": 3, "Gym Hero": 2,
            "Electric Youth": 2, "Neon Blossom": 1, "Bass Drop City": 1,
            "Pink Skies": 1, "Warm December": 1,
        },
    ),
    ScorerTest(
        label="Intense Rock - late-night drive",
        prefs={"genre": "rock", "mood": "intense", "energy": 0.90},
        expected_top_song="Storm Runner",
        expected_in_top3=["Storm Runner"],
        min_top_score=4.0,
        relevance={
            "Storm Runner": 3, "Neon Highway": 3, "Wildfire": 2,
            "Iron Curtain": 1, "Vortex Rising": 1,
        },
    ),
    ScorerTest(
        label="R&B Romantic - evening mood",
        prefs={"genre": "r&b", "mood": "romantic", "energy": 0.60},
        expected_top_song="Golden Hour Groove",
        expected_in_top3=["Golden Hour Groove"],
        min_top_score=4.0,
        relevance={
            "Golden Hour Groove": 3, "Midnight Kiss": 3, "Slow Dance": 2,
            "City Lights": 1, "Night Garden": 1,
        },
    ),
    ScorerTest(
        label="EDM Euphoric - dance floor",
        prefs={"genre": "edm", "mood": "euphoric", "energy": 0.95},
        expected_top_song="Bass Drop City",
        expected_in_top3=["Bass Drop City"],
        min_top_score=4.0,
        relevance={
            "Bass Drop City": 3, "Strobe Garden": 2, "Neon Blossom": 2,
            "Circuit Bloom": 2, "Pulse Drive": 1,
        },
    ),
    ScorerTest(
        label="Jazz chill - best genre+mood match wins",
        prefs={"genre": "jazz", "mood": "chill", "energy": 0.37},
        expected_top_song="Blue Note Evening",
        expected_in_top3=["Blue Note Evening", "Coffee Shop Stories"],
        min_top_score=4.0,
        relevance={
            "Blue Note Evening": 3, "Coffee Shop Stories": 2, "Late Set": 2,
            "Fallen Leaves": 1, "Spacewalk Thoughts": 1,
        },
    ),
    ScorerTest(
        label="Metal Intense - maximum aggression",
        prefs={"genre": "metal", "mood": "intense", "energy": 0.95},
        expected_top_song="Iron Curtain",
        expected_in_top3=["Iron Curtain"],
        min_top_score=4.0,
        relevance={
            "Iron Curtain": 3, "Vortex Rising": 3,
            "Storm Runner": 1, "Retrowave Rider": 1,
        },
    ),
    ScorerTest(
        label="Adversarial - R&B sad but high energy (genre+mood should dominate)",
        prefs={"genre": "r&b", "mood": "sad", "energy": 0.90},
        expected_top_song="Velvet Rain",
        expected_in_top3=["Velvet Rain"],
        min_top_score=3.0,
        relevance={
            "Velvet Rain": 3, "Soul Search": 2, "Blood Moon": 1,
        },
    ),
]

PARSER_TESTS = [
    ParserTest(
        label="Chill study session",
        query="something chill to study to",
        expected_genres=["lofi"],
        expected_moods=["chill", "focused"],
        energy_min=0.10,
        energy_max=0.55,
    ),
    ParserTest(
        label="Gym pump-up",
        query="pump-up music for the gym",
        expected_genres=["pop", "edm", "rock", "electronic"],
        expected_moods=["happy", "intense", "euphoric"],
        energy_min=0.60,
        energy_max=1.00,
    ),
    ParserTest(
        label="Sad rainy day",
        query="sad music for a rainy day",
        expected_genres=["indie", "r&b", "lofi"],
        expected_moods=["sad", "chill"],
        energy_min=0.00,
        energy_max=0.55,
    ),
    ParserTest(
        label="High-energy dance music",
        query="high energy songs to dance to at a party",
        expected_genres=["edm", "pop", "electronic"],
        expected_moods=["happy", "euphoric", "intense"],
        energy_min=0.65,
        energy_max=1.00,
    ),
]


# ── NDCG@k ───────────────────────────────────────────────────────────────────

def ndcg_at_k(results: list, relevance: dict, k: int = 5) -> float:
    """
    Compute NDCG@k for a ranked result list against ground-truth relevance labels.

    Relevance labels: 3=perfect, 2=good, 1=acceptable, 0=poor/absent.
    Formula: DCG / IDCG where DCG = Σ (2^rel - 1) / log2(rank + 1).
    """
    def dcg(rels: list) -> float:
        return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels[:k]))

    retrieved_rels = [relevance.get(r[0]['title'], 0) for r in results[:k]]
    ideal_rels = sorted(relevance.values(), reverse=True)

    actual = dcg(retrieved_rels)
    ideal = dcg(ideal_rels)
    return round(actual / ideal, 4) if ideal > 0 else 0.0


# ── Confidence rating ─────────────────────────────────────────────────────────

def _confidence(top_score: float, margin: float) -> str:
    if top_score >= 4.0 and margin >= 0.5:
        return "HIGH"
    if top_score >= 3.0 and margin >= 0.2:
        return "MEDIUM"
    return "LOW"


def _conf_color(conf: str) -> str:
    return {"HIGH": Fore.GREEN, "MEDIUM": Fore.YELLOW, "LOW": Fore.RED}.get(conf, "")


def _ndcg_color(score: float) -> str:
    if score >= 0.85:
        return Fore.GREEN
    if score >= 0.60:
        return Fore.YELLOW
    return Fore.RED


# ── Offline scorer tests ──────────────────────────────────────────────────────

def run_scorer_tests(songs: list) -> tuple[int, int]:
    print(f"\n{Fore.CYAN}{Style.BRIGHT}[OFFLINE] Scorer Tests  (no API required){Style.RESET_ALL}")
    print("-" * 72)

    passed = 0
    ndcg_scores = []

    for i, test in enumerate(SCORER_TESTS, 1):
        results = recommend_songs(test.prefs, songs, k=5)
        top_song, top_score, _ = results[0]
        second_score = results[1][1] if len(results) > 1 else 0.0
        margin = top_score - second_score
        top3_titles = [r[0]["title"] for r in results[:3]]

        ok_top = top_song["title"] == test.expected_top_song
        ok_score = top_score >= test.min_top_score
        ok_top3 = all(t in top3_titles for t in test.expected_in_top3)
        passed_test = ok_top and ok_score and ok_top3
        if passed_test:
            passed += 1

        ndcg = ndcg_at_k(results, test.relevance, k=5)
        ndcg_scores.append(ndcg)

        conf = _confidence(top_score, margin)
        status_str = (
            f"{Fore.GREEN}PASS{Style.RESET_ALL}"
            if passed_test
            else f"{Fore.RED}FAIL{Style.RESET_ALL}"
        )
        conf_str = f"{_conf_color(conf)}{conf}{Style.RESET_ALL}"
        ndcg_str = f"{_ndcg_color(ndcg)}{ndcg:.4f}{Style.RESET_ALL}"

        detail = (
            f"top={Style.BRIGHT}{top_song['title']!r}{Style.RESET_ALL}, "
            f"score={Fore.CYAN}{top_score:.2f}{Style.RESET_ALL}, "
            f"margin={margin:.2f}, conf={conf_str}, "
            f"NDCG@5={ndcg_str}"
        )

        reasons = []
        if not ok_top:
            reasons.append(f"expected top={test.expected_top_song!r}, got={top_song['title']!r}")
        if not ok_score:
            reasons.append(f"score {top_score:.2f} < threshold {test.min_top_score}")
        if not ok_top3:
            missing = [t for t in test.expected_in_top3 if t not in top3_titles]
            reasons.append(f"missing from top3: {missing}")

        label_padded = f"Test {i}: {test.label}"
        print(f"  {label_padded:<50}  {status_str}")
        print(f"    {detail}")
        if reasons:
            for r in reasons:
                print(f"    {Fore.RED}x {r}{Style.RESET_ALL}")

    mean_ndcg = sum(ndcg_scores) / len(ndcg_scores) if ndcg_scores else 0.0
    total = len(SCORER_TESTS)
    color = Fore.GREEN if passed == total else Fore.YELLOW
    ndcg_col = _ndcg_color(mean_ndcg)
    print(
        f"\n  {color}Scorer: {passed}/{total} passed{Style.RESET_ALL}  ·  "
        f"Mean NDCG@5: {ndcg_col}{mean_ndcg:.4f}{Style.RESET_ALL}"
    )
    return passed, total


# ── Online AI parser tests ────────────────────────────────────────────────────

def run_parser_tests() -> tuple[int, int]:
    try:
        from src.ai_recommender import parse_user_query
    except ImportError as exc:
        print(f"\n[ONLINE] Cannot import ai_recommender: {exc}")
        return 0, 0

    print(f"\n{Fore.CYAN}{Style.BRIGHT}[ONLINE] AI Parser Tests  (requires ANTHROPIC_API_KEY){Style.RESET_ALL}")
    print("-" * 72)

    passed = 0
    for i, test in enumerate(PARSER_TESTS, 1):
        try:
            prefs = parse_user_query(test.query)
        except EnvironmentError as exc:
            print(f"\n  {Fore.RED}Error: {exc}{Style.RESET_ALL}")
            print(f"  {Style.DIM}Set ANTHROPIC_API_KEY to run online tests.{Style.RESET_ALL}")
            return passed, len(PARSER_TESTS)
        except Exception as exc:
            label_padded = f"Test {i}: {test.label}"
            print(f"  {label_padded:<50}  {Fore.RED}FAIL{Style.RESET_ALL}")
            print(f"    Exception: {exc}")
            continue

        genre = prefs.get("genre", "")
        mood = prefs.get("mood", "")
        energy = prefs.get("energy", 0.0)

        ok_genre = genre in test.expected_genres
        ok_mood = mood in test.expected_moods
        ok_energy = test.energy_min <= energy <= test.energy_max

        passed_test = ok_genre and ok_mood and ok_energy
        if passed_test:
            passed += 1

        status_str = (
            f"{Fore.GREEN}PASS{Style.RESET_ALL}"
            if passed_test
            else f"{Fore.RED}FAIL{Style.RESET_ALL}"
        )
        detail = (
            f"genre={Fore.CYAN}{genre!r}{Style.RESET_ALL}, "
            f"mood={Fore.CYAN}{mood!r}{Style.RESET_ALL}, "
            f"energy={Fore.CYAN}{energy:.2f}{Style.RESET_ALL}"
        )
        reasons = []
        if not ok_genre:
            reasons.append(f"genre {genre!r} not in expected {test.expected_genres}")
        if not ok_mood:
            reasons.append(f"mood {mood!r} not in expected {test.expected_moods}")
        if not ok_energy:
            reasons.append(f"energy {energy:.2f} not in [{test.energy_min}, {test.energy_max}]")

        label_padded = f"Test {i}: {test.label}"
        print(f"  {label_padded:<50}  {status_str}")
        print(f"    {detail}")
        if reasons:
            for r in reasons:
                print(f"    {Fore.RED}x {r}{Style.RESET_ALL}")

    total = len(PARSER_TESTS)
    color = Fore.GREEN if passed == total else Fore.YELLOW
    print(f"\n  {color}Parser: {passed}/{total} passed{Style.RESET_ALL}")
    return passed, total


# ── RAG quality comparison ────────────────────────────────────────────────────

def run_rag_comparison() -> None:
    try:
        from src.ai_recommender import parse_user_query, generate_ai_explanation, get_catalog
        from src.recommender import recommend_songs as _rec
    except ImportError as exc:
        print(f"\n[RAG COMPARE] Cannot import modules: {exc}")
        return

    print("\n[RAG COMPARE] Genre Guide Quality Comparison")
    print("-" * 72)

    queries = ["something chill to study to", "pump-up music for the gym"]
    songs = get_catalog()

    for query in queries:
        print(f"\nQuery: {query!r}")
        try:
            prefs = parse_user_query(query)
            recs = _rec(prefs, songs, k=5)

            exp_without = generate_ai_explanation(query, recs, prefs, use_guide=False)
            exp_with = generate_ai_explanation(query, recs, prefs, use_guide=True)

            print("\n  WITHOUT genre guide:")
            for line in exp_without.splitlines():
                print(f"    {line}")
            print("\n  WITH genre guide (RAG Enhancement):")
            for line in exp_with.splitlines():
                print(f"    {line}")
            print()
        except EnvironmentError as exc:
            print(f"  Error: {exc}")
            return
        except Exception as exc:
            print(f"  Error: {exc}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="VibeFinder evaluation harness")
    parser.add_argument(
        "--online",
        action="store_true",
        help="Also run AI parser tests (requires ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--rag-compare",
        action="store_true",
        help="Run RAG quality comparison (requires ANTHROPIC_API_KEY)",
    )
    args = parser.parse_args()

    print("=" * 72)
    print("  VibeFinder Evaluation Harness")
    print("=" * 72)

    songs = load_songs("data/songs.csv")

    total_passed = 0
    total_tests = 0

    s_passed, s_total = run_scorer_tests(songs)
    total_passed += s_passed
    total_tests += s_total

    if args.online:
        p_passed, p_total = run_parser_tests()
        total_passed += p_passed
        total_tests += p_total

    if args.rag_compare:
        run_rag_comparison()

    if total_tests > 0:
        pct = 100 * total_passed // total_tests
        if pct == 100:
            conf_label, summary_color = "HIGH",   Fore.GREEN
        elif pct >= 75:
            conf_label, summary_color = "MEDIUM", Fore.YELLOW
        else:
            conf_label, summary_color = "LOW",    Fore.RED

        print(f"\n{summary_color}{'=' * 72}")
        print(
            f"  Overall: {total_passed}/{total_tests} passed ({pct}%)"
            f"  --  System confidence: {conf_label}"
        )
        print(f"{'=' * 72}{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
