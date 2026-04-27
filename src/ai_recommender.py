"""
RAG-based AI music recommender using the Claude API.

Pipeline:
  1. parse_user_query()       — Claude extracts structured preferences from natural language
  2. (caller runs existing scorer to retrieve top-k songs)
  3. generate_ai_explanation() — Claude explains results using retrieved songs + genre guide as context

RAG Enhancement: genre_guide.txt is a second retrieval source injected alongside song results.
Persona Support: few-shot examples constrain the explanation style (baseline / casual / dj / critic).
"""

import json
import logging
import os
import re
import anthropic
from src.recommender import load_songs, recommend_songs

# ── Logging — file only, no console noise ────────────────────────────────────
_file_handler = logging.FileHandler("recommender.log", encoding="utf-8")
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)
logging.getLogger().addHandler(_file_handler)
logging.getLogger().setLevel(logging.INFO)
# Silence third-party console output (httpx, etc.)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ── Singletons ────────────────────────────────────────────────────────────────
_client: anthropic.Anthropic | None = None
_catalog: list | None = None
_genre_guide: dict | None = None  # cached genre guide sections


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


# ── RAG Enhancement: Genre Guide retrieval ────────────────────────────────────
def _load_genre_guide() -> dict:
    """Parse genre_guide.txt into a dict keyed by genre name. Cached after first load."""
    global _genre_guide
    if _genre_guide is not None:
        return _genre_guide

    guide_path = os.path.join("data", "genre_guide.txt")
    _genre_guide = {}
    try:
        with open(guide_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Each section starts with "## genre_name"
        for section in content.split("## "):
            section = section.strip()
            if not section:
                continue
            lines = section.splitlines()
            genre_name = lines[0].strip().lower()
            body = "\n".join(lines[1:]).strip()
            _genre_guide[genre_name] = body
        logger.info("Loaded genre guide with %d genres", len(_genre_guide))
    except FileNotFoundError:
        logger.warning("genre_guide.txt not found; RAG enhancement disabled")
    return _genre_guide


def get_genre_context(genre: str) -> str:
    """
    Retrieve the genre guide entry for the given genre.
    Returns an empty string if the genre is not in the guide.
    This is the second retrieval step in the enhanced RAG pipeline.
    """
    guide = _load_genre_guide()
    return guide.get(genre.lower(), "")


# ── Step 1: Preference extraction (Claude) ────────────────────────────────────
_PARSE_SYSTEM = """\
You extract music preferences from natural language. Always respond with ONLY a JSON object.

Rules:
- "genre": pick the closest from [pop, lofi, rock, r&b, metal, indie, jazz, electronic, edm, hip-hop, country, classical, ambient, synthwave, indie pop]
- "mood": pick the closest from [happy, chill, sad, intense, focused, romantic, euphoric, nostalgic, moody, relaxed, calm]
- "energy": float 0.0 (very calm) to 1.0 (very energetic)

Mapping hints:
  workout / gym / hype / pump-up → genre=pop or electronic, mood=intense, energy 0.8-1.0
  study / focus / concentrate     → genre=lofi, mood=focused, energy 0.2-0.4
  party / dance / club            → genre=edm, mood=euphoric, energy 0.85-1.0
  sad / heartbreak / rainy        → genre=indie or r&b, mood=sad, energy 0.1-0.4
  romantic / date night           → genre=r&b, mood=romantic, energy 0.4-0.7
  chill / relax / calm            → genre=lofi or jazz, mood=chill, energy 0.1-0.4
  angry / aggressive / intense    → genre=metal or rock, mood=intense, energy 0.8-1.0
  happy / upbeat / feel-good      → genre=pop, mood=happy, energy 0.6-0.9
  late night / dark / atmospheric → genre=synthwave, mood=moody, energy 0.5-0.8
  nature / peaceful / meditative  → genre=ambient, mood=calm, energy 0.1-0.3
  nostalgic / throwback / oldies  → genre=country or indie, mood=nostalgic, energy 0.3-0.6
  classical / orchestral          → genre=classical, mood=focused, energy 0.2-0.5

If the user's current query is a refinement of a prior request (e.g. "same but sadder",
"more like that but louder"), adjust only the specified dimension and keep others the same.

Output ONLY the JSON object. No markdown, no code fences, no explanation."""


def _extract_json(raw: str) -> dict:
    """
    Robustly extract a JSON object from model output that may contain
    markdown code fences or surrounding explanation text.
    """
    text = raw.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: find the first {...} block in the text
    match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise json.JSONDecodeError("No JSON object found", text, 0)


def parse_user_query(query: str, session_prefs: dict = None) -> dict:
    """
    Use Claude to extract structured music preferences from a natural-language query.

    Args:
        query:         natural-language music request
        session_prefs: optional dict with the previous turn's {genre, mood, energy};
                       injected as context so refinement queries ("same but sadder")
                       resolve correctly without repeating genre/energy.

    Returns dict with keys: genre, mood, energy.
    Raises ValueError if Claude's response cannot be parsed as JSON.
    Raises EnvironmentError if ANTHROPIC_API_KEY is missing.
    """
    logger.info("Parsing query: %r (session_prefs=%s)", query, session_prefs)
    client = _get_client()

    if session_prefs:
        user_message = (
            f"Previous preferences: genre={session_prefs.get('genre')}, "
            f"mood={session_prefs.get('mood')}, "
            f"energy={session_prefs.get('energy', 0.5):.2f}\n"
            f"New request: {query}"
        )
    else:
        user_message = query

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=128,
            system=[
                {
                    "type": "text",
                    "text": _PARSE_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()
        logger.debug("Claude parse response: %s", raw)
        prefs = _extract_json(raw)
        prefs["energy"] = max(0.0, min(1.0, float(prefs.get("energy", 0.5))))
        logger.info("Extracted preferences: %s", prefs)
        return prefs

    except json.JSONDecodeError as exc:
        logger.error("JSON parse failed. Raw response: %r  Error: %s", raw, exc)
        raise ValueError(
            "Could not understand your request. Try describing the genre or mood directly."
        ) from exc
    except anthropic.AuthenticationError:
        logger.error("Invalid ANTHROPIC_API_KEY")
        raise
    except anthropic.APIError as exc:
        logger.error("Claude API error during preference parsing: %s", exc)
        raise


# ── Persona few-shot examples ─────────────────────────────────────────────────
# Each persona shows Claude the tone and style to use for the explanation.
# Demonstrating measurably different output from the same retrieved songs.

_PERSONA_SYSTEM = {
    "baseline": (
        "You are a music recommendation assistant. Write a warm, conversational 3-4 sentence "
        "explanation of why the retrieved songs suit the listener. Mention the top 2-3 songs "
        "by name. Be specific — reference genre, mood, or energy as appropriate. "
        "Do not repeat the scores."
    ),

    "casual": (
        "You are a friend texting music recommendations. Write like you're excited and informal — "
        "short sentences, enthusiastic, use contractions. Mention 2-3 songs by name. "
        "Keep it under 4 sentences. No scores or technical terms.\n\n"
        "EXAMPLE OUTPUT:\n"
        "omg Library Rain is exactly what you need — it's so cozy without being distracting. "
        "Midnight Coding has this soft beat that just keeps you in the zone. "
        "honestly just put these on repeat and you're set!"
    ),

    "dj": (
        "You are a professional DJ analyzing tracks for a set. Write in technical but accessible "
        "DJ/producer language — reference BPM range, energy level, texture, and how the tracks "
        "sequence together. Mention 2-3 songs by name. Keep it under 5 sentences.\n\n"
        "EXAMPLE OUTPUT:\n"
        "Opening with Library Rain — 72 BPM, sub-0.4 energy, vinyl texture keeps the floor calm "
        "without dropping tension. Midnight Coding follows at 78 BPM, stacks analog loops against "
        "ambient pads for a smooth transition. Both tracks hold consistent groove with minimal "
        "breakdown, exactly what you want for a sustained long-form session."
    ),

    "critic": (
        "You are a music critic writing a brief analytical note. Reference musical structure, "
        "production choices, and how the tracks reflect the listener's stated preferences. "
        "Formal but not dry — show genuine insight. Mention 2-3 songs by name. "
        "Keep it under 5 sentences.\n\n"
        "EXAMPLE OUTPUT:\n"
        "The selection reflects a deliberate bias toward low-energy, low-valence compositions "
        "aligned with attentional focus rather than emotional elevation. Library Rain achieves "
        "its effect through rhythmic minimalism and careful use of ambient texture, while "
        "Midnight Coding introduces marginally more structural variation without disrupting "
        "cognitive engagement. Both favour acousticness over electronic clarity — a production "
        "choice that reinforces the genre's characteristic warmth."
    ),
}


# ── Step 3: Explanation generation (Claude + retrieved songs + genre guide) ───
def generate_ai_explanation(
    user_query: str,
    recommendations: list,
    user_prefs: dict,
    persona: str = "baseline",
    use_guide: bool = True,
    on_token=None,
) -> str:
    """
    Use Claude to explain why the retrieved songs match the user's request.

    RAG pipeline (Augmented Generation step):
      - retrieved songs are injected as grounding context (primary source)
      - genre_guide.txt section is injected as background context (second source)
      - persona controls few-shot tone/style constraints

    Args:
        user_query:      original natural-language query
        recommendations: list of (song_dict, score, reasons_str) tuples
        user_prefs:      extracted {genre, mood, energy} dict
        persona:         one of 'baseline', 'casual', 'dj', 'critic'
        use_guide:       if True, inject genre guide section as second RAG source
        on_token:        optional callback(str) called for each streamed token;
                         when provided, tokens print live and the full text is returned
    """
    # Primary retrieval context: top-5 scored songs
    songs_context = "\n".join(
        f'  {i + 1}. "{s["title"]}" by {s["artist"]}'
        f' [genre={s["genre"]}, mood={s["mood"]}, energy={s["energy"]:.2f}]'
        f" — score {score:.2f} ({reasons})"
        for i, (s, score, reasons) in enumerate(recommendations)
    )

    # Second retrieval source: genre guide (RAG Enhancement)
    guide_section = ""
    if use_guide:
        ctx = get_genre_context(user_prefs.get("genre", ""))
        if ctx:
            guide_section = (
                f"\nGenre background (from music knowledge base):\n"
                f"  {ctx}\n"
            )
            logger.info("Genre guide context injected for genre=%s", user_prefs.get("genre"))
        else:
            logger.info("No genre guide entry for genre=%s", user_prefs.get("genre"))

    prompt = (
        f'A listener asked: "{user_query}"\n\n'
        f"Inferred preferences: genre={user_prefs['genre']}, "
        f"mood={user_prefs['mood']}, energy={user_prefs['energy']:.1f}\n"
        f"{guide_section}\n"
        f"Top songs retrieved from the catalog (scored by genre, mood, and energy match):\n"
        f"{songs_context}\n\n"
        "Write your explanation now."
    )

    system_text = _PERSONA_SYSTEM.get(persona, _PERSONA_SYSTEM["baseline"])
    logger.info(
        "Generating explanation -- persona=%s, use_guide=%s, songs=%d",
        persona, use_guide, len(recommendations),
    )
    client = _get_client()

    try:
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=[
                {
                    "type": "text",
                    "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            if on_token is not None:
                full_text = ""
                for token in stream.text_stream:
                    on_token(token)
                    full_text += token
                text = full_text
            else:
                final = stream.get_final_message()
                text = next(
                    (block.text for block in final.content if block.type == "text"), ""
                )

        logger.info("Explanation generated (%d chars)", len(text))
        return text

    except anthropic.APIError as exc:
        logger.error("Claude API error during explanation: %s", exc)
        raise
