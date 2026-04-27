from typing import List, Dict, Tuple


def load_songs(csv_path: str) -> List[Dict]:
    """Load songs from CSV and return list of dicts with numeric fields cast."""
    import csv
    songs = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            songs.append({
                'id': int(row['id']),
                'title': row['title'],
                'artist': row['artist'],
                'genre': row['genre'],
                'mood': row['mood'],
                'energy': float(row['energy']),
                'tempo_bpm': float(row['tempo_bpm']),
                'valence': float(row['valence']),
                'danceability': float(row['danceability']),
                'acousticness': float(row['acousticness']),
            })
    return songs


# ── Genre families for partial-credit matching ────────────────────────────────
# Related genres earn 50% of the genre weight instead of 0.
GENRE_FAMILIES: Dict[str, set] = {
    "pop":        {"pop", "indie pop"},
    "indie pop":  {"indie pop", "pop", "indie"},
    "indie":      {"indie", "indie pop"},
    "electronic": {"electronic", "edm", "synthwave"},
    "edm":        {"edm", "electronic"},
    "synthwave":  {"synthwave", "electronic"},
    "hip-hop":    {"hip-hop", "r&b"},
    "r&b":        {"r&b", "hip-hop"},
    "rock":       {"rock", "metal", "indie"},
    "metal":      {"metal", "rock"},
    "lofi":       {"lofi", "ambient"},
    "ambient":    {"ambient", "lofi"},
    "jazz":       {"jazz"},
    "classical":  {"classical"},
    "country":    {"country"},
}

# ── Mood → target valence (musical positivity 0–1) ───────────────────────────
# Used to reward songs whose valence aligns with the emotional tone requested.
MOOD_VALENCE_TARGET: Dict[str, float] = {
    "happy":     0.82,
    "euphoric":  0.90,
    "romantic":  0.78,
    "nostalgic": 0.62,
    "relaxed":   0.65,
    "calm":      0.62,
    "chill":     0.60,
    "focused":   0.55,
    "moody":     0.38,
    "sad":       0.28,
    "intense":   0.50,  # neutral — can be positive or aggressive
}

# ── Scoring mode weight presets ───────────────────────────────────────────────
SCORING_MODES: Dict[str, Dict[str, float]] = {
    "default":        {"genre": 2.0, "mood": 1.0, "energy": 1.5, "valence": 0.5, "danceability": 0.0},
    "genre-first":    {"genre": 3.5, "mood": 0.5, "energy": 0.5, "valence": 0.3, "danceability": 0.0},
    "mood-first":     {"genre": 1.0, "mood": 2.5, "energy": 1.0, "valence": 0.8, "danceability": 0.0},
    "energy-focused": {"genre": 0.5, "mood": 0.5, "energy": 3.0, "valence": 0.3, "danceability": 0.3},
    "vibe":           {"genre": 1.5, "mood": 1.5, "energy": 1.5, "valence": 1.0, "danceability": 0.5},
}


def score_song(user_prefs: Dict, song: Dict, mode: str = "default") -> Tuple[float, List[str]]:
    """Score a single song against user preferences.

    Scoring components:
      - Genre: full points for exact match; 50% for same genre family.
      - Mood: full points for exact match.
      - Energy: continuous partial credit based on absolute difference.
      - Valence: rewards songs whose musical positivity aligns with the mood.
      - Danceability: optional bonus weighted by the scoring mode.
    """
    weights = SCORING_MODES.get(mode, SCORING_MODES["default"])
    score = 0.0
    reasons = []

    # ── Genre ─────────────────────────────────────────────────────────────────
    if song['genre'] == user_prefs['genre']:
        pts = weights["genre"]
        score += pts
        reasons.append(f"genre match (+{pts})")
    else:
        family = GENRE_FAMILIES.get(user_prefs['genre'], set())
        if song['genre'] in family:
            pts = round(weights["genre"] * 0.5, 2)
            score += pts
            reasons.append(f"genre family (+{pts})")

    # ── Mood ──────────────────────────────────────────────────────────────────
    if song['mood'] == user_prefs['mood']:
        pts = weights["mood"]
        score += pts
        reasons.append(f"mood match (+{pts})")

    # ── Energy ────────────────────────────────────────────────────────────────
    energy_diff = abs(song['energy'] - user_prefs['energy'])
    energy_pts = weights["energy"] * (1 - energy_diff)
    score += energy_pts
    reasons.append(f"energy closeness (+{energy_pts:.1f})")

    # ── Valence ───────────────────────────────────────────────────────────────
    valence_w = weights.get("valence", 0.0)
    if valence_w > 0:
        target_v = MOOD_VALENCE_TARGET.get(user_prefs.get("mood", ""), 0.5)
        valence_pts = valence_w * (1 - abs(song['valence'] - target_v))
        score += valence_pts
        if valence_pts >= 0.25:
            reasons.append(f"valence fit (+{valence_pts:.1f})")

    # ── Danceability ──────────────────────────────────────────────────────────
    dance_w = weights.get("danceability", 0.0)
    if dance_w > 0:
        dance_pts = dance_w * song['danceability']
        score += dance_pts
        if dance_pts >= 0.15:
            reasons.append(f"danceability (+{dance_pts:.1f})")

    return score, reasons


def recommend_songs(
    user_prefs: Dict,
    songs: List[Dict],
    k: int = 5,
    mode: str = "default",
    diversity: bool = False,
) -> List[Tuple[Dict, float, str]]:
    """Score every song and return top-k results.

    Supports scoring modes, genre-family partial credit, valence/danceability
    signals, and optional artist-diversity deduplication.
    """
    scored = []
    for song in songs:
        score, reasons = score_song(user_prefs, song, mode=mode)
        scored.append((song, score, ", ".join(reasons)))

    scored.sort(key=lambda x: x[1], reverse=True)

    if diversity:
        seen_artists: set = set()
        diverse, penalized = [], []
        for item in scored:
            artist = item[0]['artist']
            if artist not in seen_artists:
                seen_artists.add(artist)
                diverse.append(item)
            else:
                penalized.append(item)
        scored = diverse + penalized

    return scored[:k]
