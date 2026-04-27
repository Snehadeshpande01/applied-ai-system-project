from src.recommender import score_song, recommend_songs, GENRE_FAMILIES, SCORING_MODES

POP_SONG = {
    "id": 1, "title": "Test Pop Track", "artist": "Artist A",
    "genre": "pop", "mood": "happy", "energy": 0.8,
    "tempo_bpm": 120, "valence": 0.9, "danceability": 0.8, "acousticness": 0.2,
}
LOFI_SONG = {
    "id": 2, "title": "Chill Lofi Loop", "artist": "Artist B",
    "genre": "lofi", "mood": "chill", "energy": 0.3,
    "tempo_bpm": 80, "valence": 0.55, "danceability": 0.4, "acousticness": 0.8,
}
INDIE_POP_SONG = {
    "id": 3, "title": "Indie Vibes", "artist": "Artist C",
    "genre": "indie pop", "mood": "happy", "energy": 0.75,
    "tempo_bpm": 115, "valence": 0.82, "danceability": 0.7, "acousticness": 0.3,
}


def test_perfect_match_scores_higher_than_mismatch():
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8}
    pop_score, _ = score_song(prefs, POP_SONG)
    lofi_score, _ = score_song(prefs, LOFI_SONG)
    assert pop_score > lofi_score


def test_genre_match_awards_full_points():
    prefs = {"genre": "pop", "mood": "sad", "energy": 0.5}
    score, reasons = score_song(prefs, POP_SONG)
    assert any("genre match" in r for r in reasons)


def test_genre_family_awards_partial_credit():
    # pop request → indie pop song should earn partial genre credit, not zero
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.75}
    indie_score, indie_reasons = score_song(prefs, INDIE_POP_SONG)
    no_family_song = {**INDIE_POP_SONG, "genre": "jazz"}
    jazz_score, _ = score_song(prefs, no_family_song)
    assert any("genre family" in r for r in indie_reasons)
    assert indie_score > jazz_score


def test_recommend_songs_sorted_by_score():
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8}
    results = recommend_songs(prefs, [LOFI_SONG, POP_SONG, INDIE_POP_SONG], k=3)
    assert results[0][0]["genre"] == "pop"
    scores = [score for _, score, _ in results]
    assert scores == sorted(scores, reverse=True)


def test_recommend_returns_at_most_k():
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8}
    results = recommend_songs(prefs, [POP_SONG, LOFI_SONG], k=5)
    assert len(results) <= 2


def test_diversity_filter_caps_artist_to_one():
    same_artist = [
        {**POP_SONG, "id": 1, "title": "Track 1"},
        {**POP_SONG, "id": 2, "title": "Track 2"},
        LOFI_SONG,
    ]
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8}
    results = recommend_songs(prefs, same_artist, k=3, diversity=True)
    artists = [r[0]["artist"] for r in results[:2]]
    assert len(set(artists)) == len(artists)


def test_scoring_modes_exist_and_differ():
    assert set(SCORING_MODES.keys()) == {"default", "genre-first", "mood-first", "energy-focused", "vibe"}
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8}
    default_score, _ = score_song(prefs, POP_SONG, mode="default")
    genre_score, _ = score_song(prefs, POP_SONG, mode="genre-first")
    energy_score, _ = score_song(prefs, POP_SONG, mode="energy-focused")
    assert genre_score != default_score or energy_score != default_score


def test_genre_families_cover_expected_pairs():
    assert "indie pop" in GENRE_FAMILIES["pop"]
    assert "metal" in GENRE_FAMILIES["rock"]
    assert "ambient" in GENRE_FAMILIES["lofi"]
    assert "r&b" in GENRE_FAMILIES["hip-hop"]
