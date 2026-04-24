"""
RAG-based AI music recommender using the Claude API.

Pipeline:
  1. parse_user_query()  — Claude extracts structured preferences from natural language
  2. (caller runs existing scorer to retrieve top-k songs)
  3. generate_ai_explanation() — Claude explains results using retrieved songs as context
"""

import json
import logging
import os
import anthropic
from src.recommender import load_songs, recommend_songs

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("recommender.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Singletons ────────────────────────────────────────────────────────────────
_client: anthropic.Anthropic | None = None
_catalog: list | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Export it before running: export ANTHROPIC_API_KEY=sk-ant-..."
            )
        _client = anthropic.Anthropic(api_key=api_key)
        logger.info("Anthropic client initialized")
    return _client


def get_catalog() -> list:
    """Load songs once and cache in memory."""
    global _catalog
    if _catalog is None:
        _catalog = load_songs("data/songs.csv")
        logger.info("Loaded %d songs from catalog", len(_catalog))
    return _catalog


# ── Step 1: Preference extraction (Claude) ────────────────────────────────────
_PARSE_SYSTEM = """\
You extract music preferences from user messages. Return ONLY a JSON object with exactly these keys:
- "genre": one of [pop, lofi, rock, r&b, metal, indie, jazz, electronic] — pick closest match
- "mood": one of [happy, chill, sad, intense, focused, romantic] — pick closest match
- "energy": a float between 0.0 (very calm) and 1.0 (very energetic)

Examples:
  "something chill to study to" → {"genre": "lofi", "mood": "chill", "energy": 0.3}
  "pump-up gym music" → {"genre": "pop", "mood": "intense", "energy": 0.9}
  "something sad and acoustic" → {"genre": "indie", "mood": "sad", "energy": 0.2}

Return ONLY valid JSON. No explanation, no markdown fences."""


def parse_user_query(query: str) -> dict:
    """
    Use Claude to extract structured music preferences from a natural-language query.
    Returns dict with keys: genre, mood, energy.
    Raises ValueError if Claude's response cannot be parsed as JSON.
    Raises EnvironmentError if ANTHROPIC_API_KEY is missing.
    """
    logger.info("Parsing query: %r", query)
    client = _get_client()

    try:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=128,
            system=[
                {
                    "type": "text",
                    "text": _PARSE_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": query}],
        )
        raw = response.content[0].text.strip()
        logger.debug("Claude parse response: %s", raw)
        prefs = json.loads(raw)
        # Guardrail: clamp energy to valid range
        prefs["energy"] = max(0.0, min(1.0, float(prefs.get("energy", 0.5))))
        logger.info("Extracted preferences: %s", prefs)
        return prefs

    except json.JSONDecodeError as exc:
        logger.error("JSON parse failed for Claude response: %s", exc)
        raise ValueError(
            "Could not understand your request. Try describing the genre or mood directly."
        ) from exc
    except anthropic.AuthenticationError:
        logger.error("Invalid ANTHROPIC_API_KEY")
        raise
    except anthropic.APIError as exc:
        logger.error("Claude API error during preference parsing: %s", exc)
        raise


# ── Step 3: Explanation generation (Claude + retrieved songs as context) ───────
def generate_ai_explanation(
    user_query: str, recommendations: list, user_prefs: dict
) -> str:
    """
    Use Claude to explain why the retrieved songs match the user's request.
    This is the Augmented Generation step of RAG:
      - Retrieved songs are injected as grounding context
      - Claude writes a friendly explanation anchored to those specific songs
    Returns the explanation string.
    """
    # Format retrieved songs as context (the "Retrieval" artifact fed into Claude)
    songs_context = "\n".join(
        f'  {i + 1}. "{s["title"]}" by {s["artist"]}'
        f' [genre={s["genre"]}, mood={s["mood"]}, energy={s["energy"]:.2f}]'
        f" — score {score:.2f} ({reasons})"
        for i, (s, score, reasons) in enumerate(recommendations)
    )

    prompt = (
        f'A listener asked: "{user_query}"\n\n'
        f"Inferred preferences: genre={user_prefs['genre']}, "
        f"mood={user_prefs['mood']}, energy={user_prefs['energy']:.1f}\n\n"
        f"Top songs retrieved from the catalog (scored by genre, mood, and energy match):\n"
        f"{songs_context}\n\n"
        "Write a warm, conversational 3-4 sentence explanation of why these songs "
        "suit this listener. Mention the top 2-3 songs by name. "
        "Be specific — reference the genre, mood, or energy as appropriate. "
        "Do not repeat the scores; just explain the fit naturally."
    )

    logger.info("Generating AI explanation for %d recommendations", len(recommendations))
    client = _get_client()

    try:
        with client.messages.stream(
            model="claude-opus-4-7",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            final = stream.get_final_message()

        text = next(
            (block.text for block in final.content if block.type == "text"), ""
        )
        logger.info("Explanation generated (%d chars)", len(text))
        return text

    except anthropic.APIError as exc:
        logger.error("Claude API error during explanation: %s", exc)
        raise
