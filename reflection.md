# Reflection: Profile Comparisons and Engineering Process

## Profile Pair Comparisons

**Pop vs. Lofi** — These profiles are complete opposites and the results reflect that. Pop/happy (energy=0.8) surfaces upbeat tracks with "Sunrise City" at #1; lofi/chill (energy=0.35) surfaces quiet study tracks with "Library Rain" at #1. All three scoring criteria flipped, so the recommendations flipped entirely. The system worked exactly as designed.

**Rock vs. Adversarial (r&b + sad + energy=0.9)** — Both want high energy and heavy emotion, but the outputs are very different. Rock gets a perfect #1 match ("Storm Runner", 4.48) because the catalog has one song that hits all three criteria. The adversarial r&b profile gets "Velvet Rain" at #1 — a slow ballad with energy=0.38 — because genre and mood together (+3.0 pts) overwhelm the energy penalty. The algorithm did not fail; the catalog just had no high-energy sad r&b track. This is the clearest example of data limiting results.

**Chill Lofi — no diversity vs. diversity ON** — Without diversity, LoRoom appears twice in the top 5 ("Midnight Coding" at #2, "Focus Flow" at #3). With diversity ON, Focus Flow is replaced by "Spacewalk Thoughts" from a different artist. The scores did not change — only the selection rule did. This makes the output feel more like a curated playlist than a sorted list.

**Default weights vs. weight experiment (pop/happy)** — Halving genre (2.0→1.0) and doubling energy (1.5→3.0) dropped "Gym Hero" from #2 to #4 and raised "Rooftop Lights" (indie pop/happy) to #2. One number change shifted the entire philosophy: the default rewards genre loyalty; the experiment rewards how a song actually feels.

---

## Why Does "Gym Hero" Keep Showing Up for Happy Pop Listeners?

"Gym Hero" is tagged as pop, so it earns the full +2.0 genre bonus. It is also tagged "intense" not "happy," which costs it the +1.0 mood point — but the genre bonus is so large that it still outscores every non-pop song, even ones tagged "happy." The system does not listen to music; it adds up points. As long as genre is worth double mood, any pop song beats any non-pop song regardless of how it actually sounds.

---

## Engineering Process

**Biggest learning moment:** Weights are design decisions. Changing genre from 2.0 to 1.0 reshuffled the entire top 5. Every number baked into a scoring system is a claim about what matters most — and engineers at Spotify or YouTube make those same choices at a scale that affects millions of listeners daily.

**How AI tools helped and when I double-checked:** AI was most useful for structure — CSV formatting, library suggestions, explaining `.sort()` vs `sorted()`. I had to verify the energy scoring formula by hand to confirm it rewarded closeness and not just high values. I also caught that an early version of the diversity penalty was too aggressive, which only became visible when I ran it against a real profile.

**What surprised me:** Three rules and 20 songs produced output that genuinely looked like real recommendations. The illusion comes from ranking (only the best appear) and explainability (the reasons feel logical). The system has no understanding of music — it counts matches and adds points — but it reads like it does.

---

## Scoring Modes and Genre Families

The single biggest design improvement beyond the base scorer was realising that a single weight set cannot serve every use case. A gym session is fundamentally different from a late-night ambient session — the former needs energy to dominate, the latter needs mood. This led to the five `SCORING_MODES` presets (`default`, `genre-first`, `mood-first`, `energy-focused`, `vibe`). Each is a different claim about what "good" means, and exposing them as user-selectable options makes that claim visible rather than hidden.

The genre family system came out of a concrete failure: a pop request never surfaced indie pop songs even when they were a better energy and mood match than the actual pop songs. `GENRE_FAMILIES` — a hand-authored dict of musically adjacent genres — gives related songs 50% of the genre weight instead of 0. This is a deliberate approximation. "Rock adjacent to metal" is defensible; "jazz adjacent to classical" is not, so the groupings were chosen carefully based on production and listening context overlap.

---

## AI Personas and the Explanation Layer

The four personas (`baseline`, `casual`, `dj`, `critic`) were the most interesting part of the AI layer to build, because they showed how much prompting strategy drives tone rather than model capability. All four receive identical retrieved songs. The difference between "omg Library Rain is exactly what you need — it's so cozy" (casual) and "The selection reflects a deliberate bias toward low-energy compositions aligned with attentional focus" (critic) comes entirely from a few-shot example in the system prompt, not from a larger or smarter model.

This was a useful lesson: before reaching for a more powerful model, check whether the system prompt is doing its job. The DJ persona was hardest to tune — early versions sounded generic rather than technical. It only worked once I added concrete output examples with BPM values and transition language.

---

## RAG Pipeline and the Genre Guide

The second retrieval source (`genre_guide.txt`) was added to give Claude more grounding context for genres the model might explain vaguely. Without it, explanations for niche genres like synthwave or lofi sometimes defaulted to generic praise rather than genre-specific characterisation. Injecting a paragraph of genre background alongside the scored songs gave the explanation noticeably more specificity — terms like "analog loops," "vinyl texture," and "atmospheric synthesis" appeared consistently once the guide was in context.

The key RAG design decision was keeping the genre guide as a second source rather than the primary one. The scored songs are always the primary context; the genre guide is supplementary background. This prevents hallucination: Claude can only cite songs that actually appear in the results, not ones it "knows about" from training data.

---

## Session Refinement

The session refinement feature — injecting the prior turn's `{genre, mood, energy}` preferences into the next parse call — was simple to implement but changed the interaction model significantly. Without it, "same but more intense" would fail because Claude has no memory of the prior query. With it, the parser can correctly interpret partial specifications and update only the changed dimension. The practical consequence is that users can iterate toward what they want through natural conversation rather than repeating the full specification each time.

---

## Streamlit UI Decisions

The Streamlit web interface went through several design iterations. The key decision was keeping all retrieval and scoring logic unchanged and letting the UI be a pure display layer — `app.py` calls the same `parse_user_query` and `recommend_songs` functions as the terminal interface. This means UI changes cannot accidentally alter recommendation logic, and the terminal interface remains a valid test target.

The streaming explanation in the UI uses an `on_token` callback passed to `generate_ai_explanation`. Each token updates a Streamlit placeholder, creating a live typewriter effect. The tradeoff is that each token triggers a partial re-render, which is slightly inefficient, but the perceived responsiveness matters more here than raw performance. The persona switcher regenerates the explanation only when the cache key (query + mode + persona + settings) changes — cached text is displayed immediately without re-calling the API.

---

## What I Would Try Next

Add valence to the mood matching logic so "happy" requests can score higher against high-valence songs even when the mood tag doesn't match exactly. Implement a cross-session preference store so returning users don't start from scratch. Add a confidence signal so the UI can display "weak match" for results where the top score is below 2.0.
