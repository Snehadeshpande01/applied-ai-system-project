# 🎧 Model Card: Music Recommender Simulation

## 1. Model Name

**VibeFinder 1.0**

---

## 2. Intended Use

This system suggests up to 5 songs from a 20-song catalog based on a user's preferred genre, mood, and energy level. It is designed for classroom exploration of how content-based recommenders work — not for real users or production use. It assumes the user can be described by a single fixed profile with one genre, one mood, and one energy target.

---

## 3. How the Model Works

**Step 1 — Natural language parsing (`claude-haiku-4-5`):**
The user types a free-form request ("something chill to study to"). Claude Haiku extracts three structured values: `genre`, `mood`, and `energy` (0–1 float). The system prompt is cached with `cache_control: ephemeral` so repeat calls skip re-processing it. If the user's query is a refinement ("same but more intense"), the previous turn's preferences are injected as context so only the changed dimension is updated.

**Step 2 — Deterministic scoring (`recommender.py`):**
For every song in the catalog the scorer awards points across five signals, then sorts descending and returns the top 5:

1. **Genre** — exact match earns the full genre weight (default +2.0); a related genre from `GENRE_FAMILIES` earns 50% (e.g. a pop request gets partial credit for indie pop songs).
2. **Mood** — exact string match earns the full mood weight (default +1.0).
3. **Energy** — continuous partial credit based on how close the song's energy (0–1) is to the user's target; closer = more points, up to the energy weight (default 1.5).
4. **Valence** — rewards songs whose musical positivity aligns with the mood's emotional tone (e.g. a "happy" request scores higher against high-valence songs). Weight varies by scoring mode.
5. **Danceability** — optional bonus used in `energy-focused` and `vibe` scoring modes.

Five **scoring mode** presets let users shift the weight balance: `default` (balanced), `genre-first`, `mood-first`, `energy-focused`, and `vibe` (all signals equal).

**Step 3 — AI explanation (`claude-sonnet-4-6`):**
The top-5 results plus a genre background section from `data/genre_guide.txt` (second RAG source) are injected into Claude Sonnet's context. The explanation is streamed token-by-token and shaped by one of four **personas** (baseline, casual, dj, critic), each with a few-shot example that demonstrates the required tone. The persona system prompt is also prompt-cached.

---

## 4. Data

The catalog contains 20 songs stored in `data/songs.csv`. The 10 starter songs cover pop, lofi, rock, ambient, jazz, synthwave, and indie pop. Ten additional songs were added to expand coverage into edm, hip-hop, country, classical, r&b, and metal — with moods including euphoric, nostalgic, calm, romantic, and sad. Each song has numeric fields for energy (0–1), tempo, valence, danceability, and acousticness, though only energy is used in scoring. The dataset skews toward Western popular genres and does not represent global music traditions like afrobeats, K-pop, or Latin styles.

---

## 5. Strengths

- Works well for users whose taste matches a clearly defined genre. The Chill Lofi profile returned near-perfect scores (4.50, 4.39) because the catalog has dedicated lofi songs that match on all three criteria.
- The system is fully transparent — every recommendation comes with a reason, which makes it easy to understand and debug.
- Simple enough to reason about by hand. You can predict the top result just by knowing the weights.
- The Intense Rock profile correctly surfaced "Storm Runner" first (genre + mood + energy all match), which matched intuition immediately.

---

## 6. Limitations and Bias

- **Genre dominance (in default mode):** The +2.0 genre bonus means any same-genre song can outrank a cross-genre song with a better energy and mood match. The adversarial test confirmed this — "Velvet Rain" (r&b/sad, energy=0.38) ranked #1 for a request of sad r&b at energy=0.9 because genre+mood (+3.0) outweighed the energy penalty. Switching to `energy-focused` mode shifts this balance.
- **Mood uses exact string matching:** Unlike genre (which has family-based partial credit), mood matching is binary — "focused" and "chill" are treated as completely unrelated even if the songs sound similar. A user asking for "calm" will not surface songs tagged "relaxed" or "chill."
- **Genre families are approximate:** The `GENRE_FAMILIES` dictionary gives partial credit for musically adjacent genres (pop ↔ indie pop, rock ↔ metal), but the groupings are hand-authored and subjective. A genre not in the family table earns zero credit even if it is adjacent in practice.
- **No cross-session memory:** Session refinement ("same but louder") works within a single Streamlit session but preferences reset on reload. Every fresh session starts cold.
- **Catalog-size bias:** With 70 songs, niche genre searches can still exhaust good matches by position 3–5. The system always returns 5 results and cannot signal low confidence — positions 4–5 may be energy-only matches from unrelated genres.

---

## 7. Evaluation

Four user profiles were tested and the results were compared against what a human listener would expect.

**Profile 1 — High-Energy Pop** (genre=pop, mood=happy, energy=0.8)

"Sunrise City" ranked #1 with a score of 4.47 — it matched all three criteria (pop genre, happy mood, energy=0.82). This felt exactly right. The surprise was "Gym Hero" at #2 with a score of 3.30. It is a pop song with high energy, but its mood is "intense" — not "happy." It ranked that high purely because the genre bonus (+2.0) is so strong that it carried Gym Hero above every non-pop song even without a mood match. A real listener wanting happy pop probably would not want a workout song in their top 5, but the system cannot tell the difference between "pop-happy" and "pop-intense."

**Profile 2 — Chill Lofi** (genre=lofi, mood=chill, energy=0.35)

"Library Rain" and "Midnight Coding" scored 4.50 and 4.39 respectively — both perfect matches on all three criteria. This was the most accurate-feeling result of all four tests. The only mild surprise was "Focus Flow" at #3 (score 3.42): it is a lofi song but its mood is "focused," not "chill." It ranked #3 purely because genre match (+2.0) outweighed the missing mood point. Whether a focused lofi track is a good recommendation for someone who wants chill music is debatable — instrumentally it might fit, but the label mismatch shows how much the system relies on exact tags.

**Profile 3 — Intense Rock** (genre=rock, mood=intense, energy=0.9)

"Storm Runner" ranked #1 at 4.48 — the only rock song in the catalog, so this was expected. What was interesting was positions 2 and 3: "Gym Hero" (pop/intense) and "Iron Curtain" (metal/intense) both ranked on mood match alone. They have no genre overlap with rock at all, but their "intense" mood tag earned them +1.0 each. This shows the system can surface cross-genre recommendations when mood is shared — which sometimes makes sense, and sometimes does not. A rock listener probably welcomes metal but might be confused by a pop workout track at #2.

**Profile 4 — Adversarial (genre=r&b, mood=sad, energy=0.9)**

This was the most revealing test. "Velvet Rain" ranked #1 with a score of 3.72 — it matched genre (r&b) and mood (sad), so it earned +3.0 from those alone. But its actual energy is 0.38, which is nearly the opposite of the user's target of 0.9. The energy closeness score was only +0.72 out of a possible 1.5. Despite this penalty, genre and mood together were still enough to win. This is a genuine failure: the user asked for something intense and driving, and the system returned a slow ballad because the labels matched. It confirms that the +2.0 genre weight can override meaningful numeric signals when the catalog is small.

**Weight Shift Experiment** (genre weight halved to 1.0, energy weight doubled to 3.0)

Running the pop/happy profile with adjusted weights pushed "Rooftop Lights" (indie pop/happy) from #3 to #2, overtaking "Gym Hero." With genre worth less, a song that closely matches energy and mood but sits in a related genre can finally compete. "Sunrise City" still ranked #1 because it wins on all three criteria regardless of weights. This experiment confirmed that the default scoring is genre-dominant by design, and that small weight changes have outsized effects on diversity in the results.

---

## 8. Future Work

- **Mood family matching:** Extend the genre-family partial-credit approach to mood — "chill" and "relaxed" are sonically close and should score partial credit against each other.
- **Confidence signalling:** Surface a "no good matches" message when all top-5 scores fall below a threshold, so users know the catalog lacks relevant songs rather than assuming the rankings are equally strong.
- **Genre diversity filter:** The artist diversity filter (one song per artist) is already implemented; a genre diversity variant would prevent all top-5 results from clustering in one genre.
- **Tempo (BPM) scoring:** Tempo is loaded from the CSV but not used. Matching BPM range to activity type (e.g. 60–80 BPM for studying, 120–140 for cardio) would add a meaningful fourth dimension.
- **Cross-session memory:** Persist user preferences across sessions so returning users do not start cold every time.

---

## 9. Reflection and Ethics

### What Are the Limitations or Biases in Your System?

VibeFinder has three biases worth naming explicitly:

- **Genre-dominance bias.** The +2.0 genre bonus is so large that any song matching on genre beats every cross-genre song, even when mood and energy are both wrong. The adversarial profile (r&b + sad + energy 0.9) returned a slow ballad at #1 because genre + mood combined (+3.0 pts) outweighed a near-maximum energy penalty. This is not a bug — it reflects a deliberate design choice — but it means the system will always favor stylistic familiarity over dynamic fit.
- **Exact-string genre bias.** "indie pop" is treated as completely unrelated to "pop." A pop fan never sees indie pop songs unless they happen to share a mood tag. This is a direct consequence of using `==` for matching rather than any semantic similarity, and it silently excludes a large slice of the catalog from ever competing for genre-matched profiles.
- **Catalog-size bias.** With only 20 songs, positions 3–5 in some profiles are energy-only matches from unrelated genres — not because the algorithm failed, but because there are no better options. The system cannot distinguish between "no relevant songs exist" and "no relevant songs are in this catalog," so it fills the list anyway.

### Could Your AI Be Misused, and How Would You Prevent That?

The immediate misuse risk for a music recommender is low compared to a content moderation or hiring system, but two realistic risks exist:

1. **Playlist manipulation / payola analog.** If the catalog were expanded and controlled by a commercial party, the scoring weights could be tuned to systematically surface specific songs or artists regardless of actual fit — the same genre-dominance effect that is currently a limitation would become a tool for promotion. The mitigation is weight transparency: publishing the exact formula means any bias is auditable rather than hidden.
2. **Filter bubble reinforcement.** Because the genre bonus is so strong, a user who always asks for "pop" will almost never see songs from adjacent genres, even when those songs might be a better energy or mood match. Over time this could narrow rather than expand a listener's taste. The diversity filter (`diversity=True` in `recommend_songs`) partially addresses this by capping each artist at one appearance, but it does not address genre diversity at all.

### What Surprised You While Testing Your AI's Reliability?

The most surprising result was not that the adversarial profile failed — it was designed to fail — but *how cleanly* it failed. "Velvet Rain" scored 3.72 (a comfortable margin above #2) despite its energy being 0.38 against a target of 0.9. I expected the energy penalty to at least make it close. Watching a slow ballad win a request for driving intensity by a clear margin showed that the scoring formula has a hard ceiling on how much any single continuous dimension can matter once two binary bonuses fire together.

The second surprise was how quickly the catalog limit became visible in positions 3–5. For the rock and r&b profiles, the bottom of the top-5 list was filled by songs from completely unrelated genres that happened to share an energy range. The system had no way to say "I don't have enough good matches" — it always returned five results with equal confidence, which is a quiet form of overconfidence.

### Collaboration with AI During This Project

Claude was used as a coding and design assistant throughout this project.

**Helpful suggestion:** When I was writing the query parser, Claude suggested adding `cache_control: {"type": "ephemeral"}` to the system prompt in `parse_user_query`. The reasoning was that the system prompt — which lists allowed genres, moods, and the output format — is identical on every call, so caching it means only the first call pays the full processing cost and every repeat call is faster and cheaper. This was a concrete, immediately useful improvement that I would not have reached for on my own at that stage, and it is now a core part of the architecture.

**Flawed suggestion:** Early in the design phase, Claude suggested using a second LLM call to do the ranking itself — feeding all 20 songs to Claude and asking it to pick the best five. The suggestion was framed as "more flexible" because Claude could reason about nuanced genre relationships (e.g. knowing that indie pop is adjacent to pop) in a way that exact-string matching cannot. This was wrong for the project's goals. An LLM-based ranker would be non-deterministic (two identical queries could return different ranked lists), impossible to unit-test reliably, and much harder to explain to a user. Keeping retrieval rule-based — and using Claude only at the edges for parsing and explanation — was the right call, and pushing back on that suggestion led directly to the clearest design principle in the whole system.
