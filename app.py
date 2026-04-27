"""
VibeFinder — Production Streamlit UI
Run: python -m streamlit run app.py
"""

import os
import sys
import html as _html
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

st.set_page_config(
    page_title="VibeFinder",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design tokens ─────────────────────────────────────────────────────────────
GENRE_COLORS = {
    "pop": "#ff4e6b", "lofi": "#8a7fff", "rock": "#ff7043",
    "r&b": "#ffd54f", "metal": "#78909c", "indie": "#66bb6a",
    "jazz": "#ffb74d", "electronic": "#40c4ff", "edm": "#b2ff59",
    "hip-hop": "#ffa726", "country": "#bcaaa4", "classical": "#b0bec5",
    "ambient": "#ce93d8", "synthwave": "#ea80fc", "indie pop": "#80deea",
}

GENRE_GRADIENTS = {
    "pop":        ("135deg", "#ff6b9d", "#ff2d55"),
    "lofi":       ("145deg", "#9c6bff", "#4a3aff"),
    "rock":       ("135deg", "#ff8c42", "#e53935"),
    "r&b":        ("140deg", "#ffca28", "#fb8c00"),
    "metal":      ("135deg", "#546e7a", "#1c1c2e"),
    "indie":      ("140deg", "#43a047", "#00695c"),
    "jazz":       ("135deg", "#ffa726", "#e65100"),
    "electronic": ("140deg", "#29b6f6", "#0277bd"),
    "edm":        ("135deg", "#c6ff00", "#00e676"),
    "hip-hop":    ("140deg", "#ffa000", "#e64a19"),
    "country":    ("135deg", "#a1887f", "#5d4037"),
    "classical":  ("140deg", "#78909c", "#37474f"),
    "ambient":    ("135deg", "#ba68c8", "#6a1b9a"),
    "synthwave":  ("140deg", "#e040fb", "#4a148c"),
    "indie pop":  ("135deg", "#4dd0e1", "#0097a7"),
}

GENRE_ICONS = {
    "pop": "🎵", "lofi": "☕", "rock": "🎸", "r&b": "🎤",
    "metal": "🤘", "indie": "🌿", "jazz": "🎷", "electronic": "⚡",
    "edm": "🔊", "hip-hop": "🎧", "country": "🤠", "classical": "🎻",
    "ambient": "🌊", "synthwave": "🌃", "indie pop": "🌸",
}

MOOD_EMOJIS = {
    "happy": "😄", "chill": "😌", "sad": "😢", "intense": "⚡",
    "focused": "🎯", "romantic": "💕", "euphoric": "✨",
    "nostalgic": "🌅", "moody": "🌙", "relaxed": "🛋️", "calm": "🌊",
}

PERSONA_META = {
    "baseline": ("🎵", "Music Assistant"),
    "casual":   ("😎", "Friend Mode"),
    "dj":       ("🎚️", "DJ Perspective"),
    "critic":   ("📝", "Music Critic"),
}

# Fix #12 — gradient rank colours instead of flat highlight on rank 2 only
_RANK_COLORS = {
    2: "rgba(255,45,85,0.9)",
    3: "rgba(255,255,255,0.6)",
    4: "rgba(255,255,255,0.4)",
    5: "rgba(255,255,255,0.25)",
}

# Fix #4 — clickable example queries (used as chip buttons in empty state)
# Each entry is (query_text, display_emoji)
_EXAMPLE_QUERIES = [
    ("something chill to study to",   "☕"),
    ("hype me up for the gym",         "🔥"),
    ("sad indie rainy day",            "🌧️"),
    ("late night synthwave drive",     "🌃"),
    ("romantic jazz for dinner",       "🎷"),
]

_SCORING_MODE_META = {
    "default":        ("⚖️",  "Balanced — genre · mood · energy · valence"),
    "genre-first":    ("🎸",  "Genre-first — style consistency over everything"),
    "mood-first":     ("💭",  "Mood-first — emotional feel drives results"),
    "energy-focused": ("⚡",  "Energy-focused — activity & danceability"),
    "vibe":           ("🌀",  "Vibe — all five signals equally weighted"),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

# Fix #8 — extract shared compaction logic so streaming section doesn't duplicate it
def _compact(html_str: str) -> str:
    """Strip leading whitespace per line to prevent Markdown code-block conversion."""
    return "\n".join(line.lstrip() for line in html_str.splitlines() if line.strip())


def _mhtml(html_str: str) -> None:
    st.markdown(_compact(html_str), unsafe_allow_html=True)


def _genre_css(genre: str) -> str:
    deg, c1, c2 = GENRE_GRADIENTS.get(genre, ("135deg", "#2a2a2e", "#1a1a1e"))
    return f"linear-gradient({deg},{c1},{c2})"


def _art_gradient(title: str, artist: str) -> str:
    """Deterministic unique dark gradient per song, based on title+artist."""
    seed = sum(ord(c) * (i + 3) for i, c in enumerate(title + artist))
    h1 = seed % 360
    h2 = (h1 + 50 + (seed // 180) % 75) % 360
    s  = 55 + (seed // 720) % 20
    return f"linear-gradient(145deg,hsl({h1},{s}%,26%),hsl({h2},{s-10}%,16%))"


def _score_ring(score: float, size: int = 54) -> str:
    r      = size * 0.39
    cx = cy = size / 2
    circ   = 2 * 3.14159 * r
    filled = min(score / 5.5, 1.0) * circ
    gap    = max(circ - filled, 0.01)
    color  = "#30d158" if score >= 4.0 else "#ff9f0a" if score >= 2.5 else "#ff453a"
    fs     = max(int(size * 0.22), 10)
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
        f'style="flex-shrink:0;display:block;">'
        f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" '
        f'stroke="rgba(255,255,255,0.07)" stroke-width="3.2"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" '
        f'stroke="{color}" stroke-width="3.2" '
        f'stroke-dasharray="{filled:.1f} {gap:.1f}" stroke-linecap="round" '
        f'transform="rotate(-90 {cx} {cy})"/>'
        f'<text x="{cx}" y="{cy + 4.5}" text-anchor="middle" fill="rgba(255,255,255,0.92)" '
        f'font-size="{fs}" font-weight="700" '
        f'font-family="Inter,-apple-system,sans-serif">{score:.2f}</text>'
        f'</svg>'
    )


def _energy_bar(energy: float, width: int = 72, height: int = 4) -> str:
    pct = int(energy * 100)
    if energy < 0.35:
        col = "linear-gradient(90deg,#4fc3f7,#7986cb)"
    elif energy < 0.65:
        col = "linear-gradient(90deg,#7986cb,#ba68c8)"
    elif energy < 0.85:
        col = "linear-gradient(90deg,#ba68c8,#f06292)"
    else:
        col = "linear-gradient(90deg,#f06292,#ff1744)"
    return (
        f'<div style="width:{width}px;">'
        f'<div style="font-size:10px;color:rgba(255,255,255,0.35);'
        f'text-align:right;margin-bottom:3px;font-weight:500;">{pct}%</div>'
        f'<div style="background:rgba(255,255,255,0.08);border-radius:{height}px;'
        f'height:{height}px;overflow:hidden;">'
        f'<div style="width:{pct}%;height:100%;background:{col};'
        f'border-radius:{height}px;"></div></div></div>'
    )


def _equalizer() -> str:
    return (
        '<div style="display:inline-flex;align-items:flex-end;gap:2.5px;'
        'height:18px;margin-right:8px;">'
        + "".join(
            f'<div class="eq-bar" style="animation-delay:{d}s"></div>'
            for d in [0, 0.12, 0.06, 0.18]
        )
        + "</div>"
    )


def _genre_chip(genre: str, size: str = "sm") -> str:
    col  = GENRE_COLORS.get(genre, "#8e8e93")
    icon = GENRE_ICONS.get(genre, "🎵")
    fs   = "10px" if size == "sm" else "12px"
    pad  = "2px 7px" if size == "sm" else "4px 10px"
    return (
        f'<span style="display:inline-flex;align-items:center;gap:3px;'
        f'background:rgba(0,0,0,0.3);color:{col};'
        f'border:1px solid {col}44;border-radius:20px;'
        f'padding:{pad};font-size:{fs};font-weight:700;white-space:nowrap;">'
        f'{icon} {_html.escape(genre)}</span>'
    )


def _mood_chip(mood: str) -> str:
    em = MOOD_EMOJIS.get(mood, "")
    return (
        f'<span style="display:inline-flex;align-items:center;gap:3px;'
        f'background:rgba(255,255,255,0.07);color:rgba(255,255,255,0.55);'
        f'border-radius:20px;padding:2px 7px;font-size:10px;white-space:nowrap;">'
        f'{em} {_html.escape(mood)}</span>'
    )


def _hero_card(song: dict, score: float) -> str:
    genre_grad = _genre_css(song['genre'])
    art_grad   = _art_gradient(song['title'], song['artist'])
    icon       = GENRE_ICONS.get(song['genre'], "🎵")
    mood_em    = MOOD_EMOJIS.get(song['mood'], "")
    ring       = _score_ring(score, size=76)
    e_pct      = int(song['energy'] * 100)
    # Fix #3 — 4 thresholds matching _energy_bar
    if song['energy'] < 0.35:
        e_col = "linear-gradient(90deg,#4fc3f7,#7986cb)"
    elif song['energy'] < 0.65:
        e_col = "linear-gradient(90deg,#7986cb,#ba68c8)"
    elif song['energy'] < 0.85:
        e_col = "linear-gradient(90deg,#ba68c8,#f06292)"
    else:
        e_col = "linear-gradient(90deg,#f06292,#ff1744)"

    # Fix #9 — fade-in applied here (class is now actually used)
    return f"""
<div class="fade-in" style="background:{genre_grad};border-radius:20px;padding:28px 30px;
position:relative;overflow:hidden;margin-bottom:18px;
box-shadow:0 16px 48px rgba(0,0,0,0.5);">
<div style="position:absolute;inset:0;background:rgba(0,0,0,0.32);border-radius:20px;"></div>
<div style="position:relative;z-index:2;display:flex;align-items:stretch;gap:24px;">
<div style="flex:1;min-width:0;">
<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
{_equalizer()}
<span style="font-size:10px;font-weight:700;letter-spacing:1.8px;
text-transform:uppercase;color:rgba(255,255,255,0.65);">Now Playing · Top Pick</span>
</div>
<div style="font-size:2.3rem;font-weight:800;color:#fff;line-height:1.05;
letter-spacing:-0.5px;margin-bottom:5px;
text-shadow:0 2px 12px rgba(0,0,0,0.4);">{_html.escape(song['title'])}</div>
<div style="font-size:1rem;color:rgba(255,255,255,0.6);margin-bottom:16px;
font-weight:400;">{_html.escape(song['artist'])}</div>
<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:20px;">
{_genre_chip(song['genre'], 'md')}
<span style="display:inline-flex;align-items:center;gap:3px;
background:rgba(255,255,255,0.14);color:rgba(255,255,255,0.8);
border-radius:20px;padding:4px 10px;font-size:12px;
border:1px solid rgba(255,255,255,0.2);">{mood_em} {_html.escape(song['mood'])}</span>
</div>
<div>
<div style="font-size:10px;font-weight:600;letter-spacing:1px;
text-transform:uppercase;color:rgba(255,255,255,0.45);
margin-bottom:7px;">Energy · {e_pct}%</div>
<div style="background:rgba(255,255,255,0.15);border-radius:6px;height:6px;
max-width:260px;overflow:hidden;">
<div style="width:{e_pct}%;height:100%;background:{e_col};border-radius:6px;"></div>
</div>
</div>
</div>
<div style="display:flex;flex-direction:column;align-items:center;
justify-content:space-between;gap:14px;flex-shrink:0;">
<div style="width:130px;height:130px;border-radius:14px;background:{art_grad};
box-shadow:0 8px 32px rgba(0,0,0,0.5);
display:flex;align-items:center;justify-content:center;
font-size:3.2rem;flex-shrink:0;">{icon}</div>
<div style="display:flex;flex-direction:column;align-items:center;gap:3px;">
{ring}
<span style="font-size:9px;font-weight:600;letter-spacing:1.2px;
text-transform:uppercase;color:rgba(255,255,255,0.4);">Score</span>
</div>
</div>
</div>
</div>
"""


def _track_row(rank: int, song: dict, score: float, reasons: str) -> str:
    art_grad = _art_gradient(song['title'], song['artist'])
    icon     = GENRE_ICONS.get(song['genre'], "🎵")
    ring     = _score_ring(score, size=48)
    eb       = _energy_bar(song['energy'], width=64, height=3)
    # Fix #12 — gradient rank colours
    rank_col = _RANK_COLORS.get(rank, "rgba(255,255,255,0.2)")

    tags = []
    if "genre match" in reasons:    tags.append("genre ✓")
    elif "genre family" in reasons: tags.append("genre ~")
    if "mood match" in reasons:     tags.append("mood ✓")
    if "valence fit" in reasons:    tags.append("valence ✓")
    reasons_short = " · ".join(tags)

    # Fix #9 — fade-in applied here too
    return f"""
<div class="fade-in" style="display:flex;align-items:center;gap:14px;
background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.05);
border-radius:12px;padding:12px 16px;margin-bottom:6px;
transition:background 0.15s,border-color 0.15s;"
onmouseenter="this.style.background='rgba(255,255,255,0.06)';this.style.borderColor='rgba(255,255,255,0.1)'"
onmouseleave="this.style.background='rgba(255,255,255,0.03)';this.style.borderColor='rgba(255,255,255,0.05)'">
<div style="font-size:14px;font-weight:700;color:{rank_col};
min-width:20px;text-align:center;flex-shrink:0;">{rank}</div>
<div style="width:44px;height:44px;border-radius:8px;background:{art_grad};
display:flex;align-items:center;justify-content:center;
font-size:1.3rem;flex-shrink:0;box-shadow:0 4px 12px rgba(0,0,0,0.4);">{icon}</div>
<div style="flex:1;min-width:0;">
<div style="font-size:14px;font-weight:600;color:rgba(255,255,255,0.88);
white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_html.escape(song['title'])}</div>
<div style="font-size:12px;color:rgba(255,255,255,0.38);margin-top:2px;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_html.escape(song['artist'])}</div>
<div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:5px;">
{_genre_chip(song['genre'])}
{_mood_chip(song['mood'])}
{('<span style="font-size:10px;color:rgba(255,255,255,0.28);padding:2px 4px;">' + reasons_short + '</span>') if reasons_short else ''}
</div>
</div>
<div style="flex-shrink:0;">{eb}</div>
<div style="flex-shrink:0;">{ring}</div>
</div>
"""


def _explanation_card(text: str, persona: str, cursor: bool = False) -> str:
    icon, label = PERSONA_META.get(persona, ("🎵", persona.title()))
    cur = '<span style="animation:blink 1s step-end infinite;opacity:1;">▌</span>' if cursor else ""

    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paras and text.strip():
        paras = [text.strip()]
    body_html = "".join(
        f'<p style="margin:0 0 14px;color:rgba(255,255,255,0.75);'
        f'font-size:15px;line-height:1.75;">{p.replace(chr(10), "<br>")}</p>'
        for p in paras
    )

    return f"""
<div style="background:rgba(20,20,22,0.9);border:1px solid rgba(255,78,107,0.2);
border-radius:18px;padding:26px 28px;margin-top:20px;
box-shadow:0 8px 32px rgba(0,0,0,0.3);">
<div style="display:flex;align-items:center;gap:10px;
padding-bottom:14px;margin-bottom:16px;
border-bottom:1px solid rgba(255,255,255,0.06);">
<span style="font-size:1.2rem;">{icon}</span>
<div>
<div style="font-size:11px;font-weight:700;letter-spacing:1.2px;
text-transform:uppercase;color:#ff6b9d;">{label}</div>
<div style="font-size:11px;color:rgba(255,255,255,0.28);margin-top:1px;">
AI-generated · Claude Sonnet
</div>
</div>
</div>
<div>{body_html}{cur}</div>
</div>
"""


# Fix #1 — XSS: escape user-supplied text injected into HTML
def _history_row(entry: dict) -> str:
    g    = entry['prefs'].get('genre', '—')
    icon = GENRE_ICONS.get(g, "🎵")
    col  = GENRE_COLORS.get(g, '#8e8e93')
    raw  = entry['query']
    q    = _html.escape(raw[:42]) + ("…" if len(raw) > 42 else "")
    return (
        f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.05);'
        f'border-radius:10px;padding:9px 12px;margin-bottom:5px;">'
        f'<div style="display:flex;align-items:center;gap:7px;">'
        f'<span style="font-size:13px;">{icon}</span>'
        f'<div style="min-width:0;">'
        f'<div style="font-size:12px;font-weight:500;color:rgba(255,255,255,0.7);'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{q}</div>'
        f'<div style="font-size:10px;color:rgba(255,255,255,0.28);margin-top:1px;">'
        f'<span style="color:{col};">{_html.escape(g)}</span>'
        f' · {_html.escape(entry["prefs"].get("mood", "—"))}</div>'
        f'</div></div></div>'
    )


# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,300..900;1,14..32,300..900&display=swap');

/* ── Base ───────────────────────────────────── */
html,body,[class*="st-"]{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'SF Pro Display',sans-serif!important;
}
.stApp{background:#0a0a0b!important;}

/* Hide Streamlit chrome */
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding-top:1.8rem!important;padding-bottom:3rem!important;max-width:1160px;}

/* ── Sidebar: force always visible ─────────── */
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#111115 0%,#0d0d10 100%)!important;
  border-right:1px solid rgba(255,255,255,0.05)!important;
  min-width:260px!important;max-width:260px!important;width:260px!important;
  transform:translateX(0)!important;display:flex!important;visibility:visible!important;
}
[data-testid="stSidebar"][aria-expanded="false"]{
  transform:translateX(0)!important;
  min-width:260px!important;max-width:260px!important;width:260px!important;
  display:flex!important;visibility:visible!important;opacity:1!important;
}
button[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarNavCollapseButton"],
[data-testid="collapsedControl"],
button[title="Close sidebar"],button[title="Open sidebar"],
button[aria-label="Close sidebar"],button[aria-label="Open sidebar"],
section[data-testid="stSidebar"]>div>button,
section[data-testid="stSidebar"]>div>button:first-child,
section[data-testid="stSidebar"]>div>button:first-of-type{
  display:none!important;visibility:hidden!important;
  pointer-events:none!important;width:0!important;height:0!important;
  overflow:hidden!important;opacity:0!important;
}
[data-testid="stSidebar"] *{color:rgba(255,255,255,0.82)!important;}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stCheckbox label{
  color:rgba(255,255,255,0.45)!important;
  font-size:11px!important;font-weight:600!important;letter-spacing:0.6px!important;
}

/* ── Form submit button (primary red) ───────── */
button[data-testid="stFormSubmitButton"],
button[data-testid="stFormSubmitButton"] p{
  background:linear-gradient(135deg,#ff4e6b 0%,#e5003e 100%)!important;
  color:#fff!important;border:none!important;border-radius:12px!important;
  font-weight:700!important;font-size:15px!important;
  padding:0 24px!important;height:52px!important;width:100%!important;
  letter-spacing:0.2px!important;cursor:pointer!important;
  box-shadow:0 4px 20px rgba(255,45,85,0.35)!important;
  transition:transform 0.15s ease,box-shadow 0.15s ease!important;
}
button[data-testid="stFormSubmitButton"]:hover{
  transform:translateY(-1px)!important;
  box-shadow:0 8px 28px rgba(255,45,85,0.5)!important;
}
button[data-testid="stFormSubmitButton"]:active{transform:scale(0.98)!important;}

/* ── All other buttons (chip / action style) ── */
.stButton>button{
  background:rgba(30,30,34,0.85)!important;
  border:1px solid rgba(255,255,255,0.09)!important;
  border-radius:20px!important;color:rgba(255,255,255,0.55)!important;
  font-size:12px!important;font-weight:500!important;
  padding:0 14px!important;height:34px!important;
  box-shadow:none!important;letter-spacing:0!important;
  cursor:pointer!important;transition:all 0.15s ease!important;
}
.stButton>button:hover{
  background:rgba(255,78,107,0.1)!important;
  border-color:rgba(255,78,107,0.3)!important;
  color:rgba(255,255,255,0.85)!important;
  transform:translateY(-1px)!important;
}
.stButton>button:active{transform:scale(0.98)!important;}

/* Sidebar clear-history button: full-width, slightly red tint */
[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] .stButton>button{
  border-radius:10px!important;width:100%!important;
  background:rgba(255,78,107,0.1)!important;
  border-color:rgba(255,78,107,0.2)!important;
  color:rgba(255,255,255,0.6)!important;
}
[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] .stButton>button:hover{
  background:rgba(255,78,107,0.2)!important;
  border-color:rgba(255,78,107,0.4)!important;
  color:#fff!important;
}

/* ── Text input ─────────────────────────────── */
.stTextInput>div>div>input{
  background:rgba(30,30,34,0.95)!important;
  border:1.5px solid rgba(255,255,255,0.08)!important;
  border-radius:14px!important;color:rgba(255,255,255,0.9)!important;
  font-size:15px!important;padding:14px 18px!important;height:52px!important;
  caret-color:#ff4e6b!important;
  transition:border-color 0.2s,box-shadow 0.2s!important;
}
.stTextInput>div>div>input:focus{
  border-color:rgba(255,78,107,0.55)!important;
  box-shadow:0 0 0 3px rgba(255,78,107,0.12)!important;outline:none!important;
}
.stTextInput>div>div>input::placeholder{color:rgba(255,255,255,0.2)!important;}
.stTextInput label{
  font-size:10px!important;font-weight:700!important;letter-spacing:1.4px!important;
  text-transform:uppercase!important;color:rgba(255,255,255,0.35)!important;
  margin-bottom:6px!important;
}

/* ── Selectbox ──────────────────────────────── */
.stSelectbox>div>div{
  background:rgba(30,30,34,0.9)!important;
  border:1px solid rgba(255,255,255,0.08)!important;
  border-radius:10px!important;color:rgba(255,255,255,0.8)!important;
  font-size:13px!important;
}
.stSelectbox label{color:rgba(255,255,255,0.4)!important;font-size:11px!important;}

/* ── Radio tabs ─────────────────────────────── */
div[data-testid="stRadio"]>label{
  color:rgba(255,255,255,0.45)!important;
  font-size:11px!important;font-weight:700!important;letter-spacing:0.8px!important;
}
div[data-testid="stRadio"]>div{gap:6px!important;flex-wrap:wrap!important;}
div[data-testid="stRadio"]>div>label{
  background:rgba(30,30,34,0.8)!important;
  border:1px solid rgba(255,255,255,0.07)!important;
  border-radius:10px!important;padding:7px 14px!important;
  font-size:12px!important;color:rgba(255,255,255,0.55)!important;
  cursor:pointer!important;transition:all 0.15s ease!important;
}
div[data-testid="stRadio"]>div>label:hover{
  background:rgba(255,78,107,0.12)!important;
  border-color:rgba(255,78,107,0.35)!important;
  color:rgba(255,255,255,0.85)!important;
}
div[data-testid="stRadio"]>div>label[data-baseweb="radio"]:has(input:checked){
  background:rgba(255,78,107,0.18)!important;
  border-color:rgba(255,78,107,0.5)!important;
  color:#ff8fa3!important;
}

/* ── Checkbox ───────────────────────────────── */
.stCheckbox label{display:flex;align-items:center;gap:8px;cursor:pointer;}
.stCheckbox label span{color:rgba(255,255,255,0.65)!important;font-size:13px!important;}

/* ── Section label ──────────────────────────── */
.sec-label{
  font-size:10px;font-weight:700;letter-spacing:1.8px;
  text-transform:uppercase;color:rgba(255,255,255,0.28);
  margin-bottom:12px;margin-top:4px;padding-left:2px;
}

/* ── Divider ────────────────────────────────── */
hr.vf{border:none;border-top:1px solid rgba(255,255,255,0.06);margin:18px 0;}

/* ── Spinner ────────────────────────────────── */
.stSpinner>div{border-top-color:#ff4e6b!important;}

/* ── Animations ─────────────────────────────── */
@keyframes eq{0%,100%{transform:scaleY(0.4);}50%{transform:scaleY(1.0);}}
.eq-bar{
  width:3px;height:16px;background:#ff4e6b;border-radius:2px;
  transform-origin:bottom;animation:eq 0.75s ease-in-out infinite;
}
@keyframes blink{0%,100%{opacity:1;}50%{opacity:0;}}
/* Fix #9 — fade-in is now used on hero card and track rows */
@keyframes fadeIn{from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:none;}}
.fade-in{animation:fadeIn 0.35s ease forwards;}

/* ── Scrollbar ──────────────────────────────── */
::-webkit-scrollbar{width:4px;height:4px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.12);border-radius:2px;}
::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,0.25);}

/* ── Empty-state icon: float + glow ─────────── */
@keyframes float{
  0%,100%{transform:translateY(0px);}
  50%{transform:translateY(-14px);}
}
@keyframes pulse-glow{
  0%,100%{filter:drop-shadow(0 0 22px rgba(255,78,107,0.3)) drop-shadow(0 0 8px rgba(206,147,216,0.15));}
  50%{filter:drop-shadow(0 0 64px rgba(255,78,107,0.75)) drop-shadow(0 0 120px rgba(206,147,216,0.3));}
}
.es-icon{
  animation:float 3.4s ease-in-out infinite, pulse-glow 3.4s ease-in-out infinite;
  display:inline-block;
}

/* ── Logo shimmer ───────────────────────────── */
@keyframes logo-shimmer{
  0%{background-position:0% 50%;}
  50%{background-position:100% 50%;}
  100%{background-position:0% 50%;}
}
.vf-logo{
  background:linear-gradient(135deg,#ff4e6b,#ff8fa3,#ce93d8,#ff4e6b);
  background-size:200% 200%;
  animation:logo-shimmer 4s ease infinite;
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;
}

/* ── How-it-works step cards ─────────────────── */
.step-card{
  background:rgba(255,255,255,0.03);
  border:1px solid rgba(255,255,255,0.07);
  border-radius:16px;padding:22px 18px;text-align:center;
  transition:border-color 0.2s, background 0.2s;
}
.step-card:hover{
  background:rgba(255,255,255,0.055);
  border-color:rgba(255,78,107,0.25);
}

/* ── Suggestion chips (empty-state buttons) ──── */
/* Taller, more readable, more inviting default state */
.stButton>button{height:40px!important;}

/* ── Search hint text ───────────────────────── */
.search-hint{
  font-size:11px;color:rgba(255,255,255,0.2);
  margin-top:6px;padding-left:2px;
  letter-spacing:0.3px;
}
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────
for _k, _v in {
    "results": None, "prefs": None, "explanation": "",
    "query": "", "history": [], "last_prefs": None, "_exp_key": "",
    "search_query": "",
    "_pending_query": "",   # staged query written before text-input is instantiated
    "_submit_now": False,   # Fix #4 / #5 — chip + history replay auto-submit
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# Apply any pending query BEFORE the text-input widget is instantiated.
# Streamlit forbids writing a widget's bound key after the widget renders.
if st.session_state._pending_query:
    st.session_state.search_query = st.session_state._pending_query
    st.session_state._pending_query = ""


@st.cache_resource(show_spinner=False)
def _load_catalog():
    from src.recommender import load_songs
    return load_songs("data/songs.csv")


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="padding:8px 0 4px;">'
        '<div class="vf-logo" style="font-size:22px;font-weight:800;'
        'letter-spacing:-0.5px;">♪ VibeFinder</div>'
        '<div style="font-size:11px;color:rgba(255,255,255,0.28);'
        'font-weight:400;margin-top:2px;">AI-powered music discovery</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<hr class="vf">', unsafe_allow_html=True)
    st.markdown('<div class="sec-label">⚙ Discover Settings</div>', unsafe_allow_html=True)

    scoring_mode = st.selectbox(
        "Scoring Mode",
        ["default", "genre-first", "mood-first", "energy-focused", "vibe"],
        index=0,
        help=(
            "⚖️  default — balanced (genre·mood·energy·valence)\n"
            "🎸  genre-first — genre heavily weighted\n"
            "💭  mood-first — mood & valence drive results\n"
            "⚡  energy-focused — energy + danceability\n"
            "🌀  vibe — all five signals equally weighted"
        ),
    )

    # Show a quick description of the active scoring mode
    _sm_icon, _sm_desc = _SCORING_MODE_META.get(scoring_mode, ("⚖️", ""))
    st.markdown(
        f'<div style="font-size:10px;color:rgba(255,255,255,0.28);'
        f'margin-top:4px;margin-bottom:2px;padding:6px 8px;'
        f'background:rgba(255,255,255,0.03);border-radius:8px;line-height:1.5;">'
        f'{_sm_icon} {_sm_desc}</div>',
        unsafe_allow_html=True,
    )

    # Fix #6 — persona removed from sidebar; single source of truth is the
    # inline radio in the results section, so settings don't diverge.

    use_rag       = st.checkbox("Use genre guide (RAG)", value=True)
    use_diversity = st.checkbox("Artist diversity filter", value=False)

    st.markdown('<hr class="vf">', unsafe_allow_html=True)
    st.markdown('<div class="sec-label">🕒 Session History</div>', unsafe_allow_html=True)

    if st.session_state.history:
        # Fix #5 — each history entry has a replay button
        for i, entry in enumerate(reversed(st.session_state.history[-6:])):
            col_h, col_r = st.columns([5, 1])
            with col_h:
                _mhtml(_history_row(entry))
            with col_r:
                if st.button("↩", key=f"replay_{i}", help="Re-run this search"):
                    st.session_state._pending_query = entry["query"]
                    st.session_state._submit_now    = True
                    st.rerun()
        if st.button("Clear history", use_container_width=True):
            st.session_state.history     = []
            st.session_state.last_prefs  = None
            st.session_state.results     = None
            st.session_state.explanation = ""
            st.rerun()
    else:
        st.markdown(
            '<p style="color:rgba(255,255,255,0.2);font-size:12px;padding:4px 2px;">'
            'No searches yet.</p>',
            unsafe_allow_html=True,
        )

    st.markdown('<hr class="vf">', unsafe_allow_html=True)
    try:
        _songs  = _load_catalog()
        _genres = len({s['genre'] for s in _songs})
        st.markdown(
            f'<div style="font-size:11px;color:rgba(255,255,255,0.2);'
            f'padding:0 2px;line-height:1.8;">'
            f'Catalog: <b style="color:rgba(255,255,255,0.4);">{len(_songs)}</b> songs<br>'
            f'Genres: <b style="color:rgba(255,255,255,0.4);">{_genres}</b> &nbsp;·&nbsp; '
            f'Scorer: <b style="color:rgba(255,255,255,0.4);">v2</b></div>',
            unsafe_allow_html=True,
        )
    except Exception:
        pass


# ── Main content ──────────────────────────────────────────────────────────────
st.markdown(
    '<div style="text-align:center;margin-bottom:32px;">'
    '<div class="vf-logo" style="font-size:2.6rem;font-weight:800;'
    'letter-spacing:-1px;line-height:1.05;">♪ VibeFinder</div>'
    '<div style="font-size:14px;color:rgba(255,255,255,0.3);margin-top:6px;font-weight:400;">'
    'Describe your mood &nbsp;·&nbsp; Claude finds your music</div>'
    '</div>',
    unsafe_allow_html=True,
)

# ── Search form ───────────────────────────────────────────────────────────────
with st.form("vf_search", clear_on_submit=False):
    col_q, col_b = st.columns([5, 1])
    with col_q:
        st.text_input(
            "WHAT ARE YOU IN THE MOOD FOR?",
            placeholder='"chill study beats" · "pump me up for the gym" · "same but more intense"',
            key="search_query",
        )
        st.markdown(
            '<div class="search-hint">💡 Tip: chain requests — try "same but more upbeat" or "something slower"</div>',
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown('<div style="height:27px;"></div>', unsafe_allow_html=True)
        submitted = st.form_submit_button("Find Music", use_container_width=True)

# ── Process submission (form submit OR auto-submit from chip/history replay) ──
_auto = st.session_state.get("_submit_now", False)
if _auto:
    st.session_state._submit_now = False

query_input = st.session_state.get("search_query", "").strip()

if (submitted or _auto) and query_input:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("⚠️  ANTHROPIC_API_KEY is not set. Run: export ANTHROPIC_API_KEY=sk-ant-...")
        st.stop()

    songs = _load_catalog()
    with st.spinner("Tuning into your vibe…"):
        try:
            from src.ai_recommender import parse_user_query
            prefs = parse_user_query(query_input, session_prefs=st.session_state.last_prefs)
        except EnvironmentError as e:
            st.error(str(e))
            st.stop()
        except Exception as e:
            st.error(f"Couldn't parse that request: {e}")
            st.stop()

        from src.recommender import recommend_songs
        results = recommend_songs(prefs, songs, k=5, mode=scoring_mode, diversity=use_diversity)

    # Fix #7 — surface empty results rather than silently showing nothing
    if not results:
        st.warning("No songs matched that vibe. Try a different mood, genre, or scoring mode.")
        st.stop()

    st.session_state.results     = results
    st.session_state.prefs       = prefs
    st.session_state.query       = query_input
    st.session_state.explanation = ""
    st.session_state._exp_key    = ""
    st.session_state.last_prefs  = prefs
    st.session_state.history.append({
        "query": query_input, "prefs": prefs,
        "top_song": results[0][0]['title'],
    })
    st.rerun()

# ── Results ───────────────────────────────────────────────────────────────────
if st.session_state.results:
    results = st.session_state.results
    prefs   = st.session_state.prefs
    query   = st.session_state.query

    # Preference + scoring-mode chips
    st.markdown('<hr class="vf">', unsafe_allow_html=True)
    g_col  = GENRE_COLORS.get(prefs.get('genre', ''), '#ff4e6b')
    g_icon = GENRE_ICONS.get(prefs.get('genre', ''), '🎵')
    m_em   = MOOD_EMOJIS.get(prefs.get('mood', ''), '')
    e_pct  = int(prefs.get('energy', 0) * 100)

    def _pref_chip(label: str, value: str, color: str = "rgba(255,255,255,0.6)") -> str:
        return (
            f'<span style="display:inline-flex;align-items:center;gap:5px;'
            f'background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.09);'
            f'color:{color};padding:5px 12px;border-radius:20px;font-size:12px;">'
            f'<span style="font-size:9px;letter-spacing:1px;text-transform:uppercase;'
            f'color:rgba(255,255,255,0.25);">{label}</span>{value}</span>'
        )

    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px;">'
        + _pref_chip("genre", f'<span style="color:{g_col};font-weight:600;">{g_icon} {_html.escape(prefs.get("genre",""))}</span>')
        + _pref_chip("mood",  f'{m_em} {_html.escape(prefs.get("mood",""))}')
        + _pref_chip("energy", f'{e_pct}%')
        # Fix #11 — scoring mode shown here instead of in the now-removed metrics strip
        + _pref_chip("mode",  _html.escape(scoring_mode))
        + '</div>',
        unsafe_allow_html=True,
    )

    # Hero card
    top_song, top_score, top_reasons = results[0]
    _mhtml(_hero_card(top_song, top_score))

    # Track list
    if len(results) > 1:
        st.markdown('<div class="sec-label" style="margin-top:6px;">Up Next</div>', unsafe_allow_html=True)
        for rank, (song, score, reasons) in enumerate(results[1:], 2):
            _mhtml(_track_row(rank, song, score, reasons))

    # Fix #11 — metrics strip removed (it duplicated hero card info).
    # Scoring mode is now in the preference chip bar above.

    # AI Explanation
    st.markdown('<hr class="vf">', unsafe_allow_html=True)
    st.markdown('<div class="sec-label">AI Explanation</div>', unsafe_allow_html=True)

    # Fix #6 — single persona control here; sidebar selectbox removed
    persona_choice = st.radio(
        "Persona",
        options=["baseline", "casual", "dj", "critic"],
        format_func=lambda p: f"{PERSONA_META[p][0]}  {PERSONA_META[p][1]}",
        horizontal=True,
        label_visibility="collapsed",
    )

    # Fix #2 — use_diversity included in cache key
    cache_key = f"{query}|{scoring_mode}|{persona_choice}|{use_rag}|{use_diversity}"

    if st.session_state.get("_exp_key") != cache_key:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            st.error("⚠️  ANTHROPIC_API_KEY not set.")
        else:
            placeholder = st.empty()
            placeholder.markdown(
                _compact(_explanation_card("", persona_choice, cursor=True)),
                unsafe_allow_html=True,
            )
            buf = [""]

            # Fix #10 — renamed html → card_html to avoid shadowing _html module
            def _on_tok(t: str) -> None:
                buf[0] += t
                card_html = _explanation_card(buf[0], persona_choice, cursor=True)
                placeholder.markdown(_compact(card_html), unsafe_allow_html=True)

            try:
                from src.ai_recommender import generate_ai_explanation
                generate_ai_explanation(
                    query, results, prefs,
                    persona=persona_choice, use_guide=use_rag,
                    on_token=_on_tok,
                )
            except Exception as exc:
                buf[0] = f"(Could not generate explanation: {exc})"

            placeholder.markdown(
                _compact(_explanation_card(buf[0], persona_choice, cursor=False)),
                unsafe_allow_html=True,
            )
            st.session_state.explanation = buf[0]
            st.session_state["_exp_key"] = cache_key
    else:
        _mhtml(_explanation_card(st.session_state.explanation, persona_choice))

# ── Empty state ───────────────────────────────────────────────────────────────
else:
    st.markdown('<hr class="vf">', unsafe_allow_html=True)

    # Hero section: animated icon + headline
    st.markdown(
        '<div style="text-align:center;padding:48px 24px 12px;">'
        '<div class="es-icon" style="font-size:4.5rem;margin-bottom:22px;'
        'display:inline-block;">🎵</div>'
        '<div style="font-size:1.45rem;font-weight:800;letter-spacing:-0.3px;'
        'background:linear-gradient(135deg,#fff 40%,rgba(255,255,255,0.45));'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;'
        'background-clip:text;margin-bottom:10px;">Your music is waiting</div>'
        '<div style="font-size:13px;color:rgba(255,255,255,0.28);'
        'line-height:1.8;max-width:380px;margin:0 auto;">'
        'Type any mood, activity, or feeling — Claude parses your vibe '
        'and deterministic scoring finds your tracks.'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # How it works — 3-step cards
    st.markdown('<div style="height:28px;"></div>', unsafe_allow_html=True)
    step_cols = st.columns(3)
    _steps = [
        ("✍️", "Describe a vibe", "Use natural language: mood, activity, genre, tempo — anything."),
        ("🤖", "Claude parses it", "AI extracts genre, mood & energy preferences from your words."),
        ("🎯", "Scores find your tracks", "Deterministic scoring ranks the best matches from the catalog."),
    ]
    for col, (icon, title, body) in zip(step_cols, _steps):
        col.markdown(
            f'<div class="step-card fade-in">'
            f'<div style="font-size:2rem;margin-bottom:12px;">{icon}</div>'
            f'<div style="font-size:13px;font-weight:700;color:rgba(255,255,255,0.75);'
            f'margin-bottom:6px;">{title}</div>'
            f'<div style="font-size:11px;color:rgba(255,255,255,0.3);line-height:1.7;">{body}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Suggestion chips
    st.markdown('<div style="height:28px;"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="text-align:center;font-size:10px;font-weight:700;'
        'letter-spacing:1.8px;text-transform:uppercase;'
        'color:rgba(255,255,255,0.22);margin-bottom:14px;">✦ Try these vibes ✦</div>',
        unsafe_allow_html=True,
    )

    # Row 1: first 3 chips
    chip_row1 = st.columns(3)
    for col, (label, icon) in zip(chip_row1, _EXAMPLE_QUERIES[:3]):
        if col.button(f"{icon}  {label}", use_container_width=True):
            st.session_state._pending_query = label
            st.session_state._submit_now    = True
            st.rerun()

    # Row 2: last 2 chips centered
    _, c_left, c_right, _ = st.columns([0.5, 1, 1, 0.5])
    for col, (label, icon) in zip([c_left, c_right], _EXAMPLE_QUERIES[3:]):
        if col.button(f"{icon}  {label}", use_container_width=True):
            st.session_state._pending_query = label
            st.session_state._submit_now    = True
            st.rerun()

    st.markdown('<div style="height:40px;"></div>', unsafe_allow_html=True)
