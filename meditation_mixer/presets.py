"""Content type presets: Meditation and Sleep Story.

Pure data module defining per-content-type defaults for the audio pipeline.
These presets drive both TTS parameters and mix settings, allowing the app to
support multiple content types (meditation, sleep story, etc.) without code duplication.
Presets are immutable (frozen dataclass) to prevent accidental mutation.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContentPreset:
    """Immutable preset for a content type (meditation, sleep story, etc.).

    Holds all the tuned defaults for both the TTS synthesis and the mixing pipeline,
    plus UI metadata (label, guide, placeholder text). When a user selects a
    content type, these values populate the sidebar sliders and text areas.
    """

    # --- Metadata ---
    key: str
    """Stable identifier: 'meditation' or 'sleep_story'. Used internally."""

    label: str
    """UI label shown in the Streamlit selectbox (e.g. 'Meditation')."""

    guide_file: str
    """Filename of the script-writing guide for this content type."""

    render_prefix: str
    """Stem of the output filename (e.g. 'meditation_<timestamp>.wav')."""

    # --- TTS defaults ---
    pause_scale: float
    """Stretches silence in the script. Higher = more spacious pacing."""

    tone_preset: str
    """Audio tags prepended at chunk boundaries (e.g. '[soft][slowly]')."""

    inter_chunk_silence_ms: float
    """Silence injected between synthesized speech chunks (milliseconds)."""

    max_chunk_chars: int | None
    """Max characters per TTS request. None = use config default (800 chars)."""

    stability: float
    """Voice stability (0.0–1.0). ~0.50 balances warmth with consistency."""

    ramp_pause_end_scale: float
    """Pause-lengthening multiplier toward end of track. 1.0 = off."""

    # --- Mix defaults (subset of MixSettings) ---
    bg_gain_db: float
    """Background music gain in decibels."""

    duck_range_db: float
    """Maximum ducking attenuation (negative dB) during speech."""

    duck_release_ms: float
    """Milliseconds for music to swell back after ducking."""

    duck_lift_db: float
    """Music lift (boost) during long pauses, in decibels."""

    # --- UI copy ---
    placeholder: str
    """Example text shown in the script textarea as a starting point."""


# ============================================================================
# MEDITATION preset: mirrors today's exact app defaults
# ============================================================================
MEDITATION = ContentPreset(
    key="meditation",
    label="Meditation",
    guide_file="docs/MEDITATION_GUIDE.md",
    render_prefix="meditation",
    pause_scale=2.0,
    tone_preset="[soft][slowly]",
    inter_chunk_silence_ms=300.0,
    max_chunk_chars=None,
    stability=0.50,
    ramp_pause_end_scale=1.0,
    bg_gain_db=-13.0,
    duck_range_db=-7.0,
    duck_release_ms=1200.0,
    duck_lift_db=2.0,
    placeholder=(
        "[soft] Welcome.  Find a comfortable position…\n\n"
        "[gentle] And when you're ready, [breathes] gently close your eyes.\n\n"
        "[pause for 5 seconds]\n\n"
        "[calm] Take a slow breath in… [inhales]\n\n"
        "[soft] …and let it go. [exhales]"
    ),
)

# ============================================================================
# SLEEP_STORY preset: optimized for longer, slower narratives
# ============================================================================
SLEEP_STORY = ContentPreset(
    key="sleep_story",
    label="Sleep Story",
    guide_file="docs/SLEEP_STORY_GUIDE.md",
    render_prefix="sleep_story",
    pause_scale=1.1,
    tone_preset="[calm][soft]",
    inter_chunk_silence_ms=200.0,
    max_chunk_chars=1600,
    stability=0.50,
    ramp_pause_end_scale=1.6,
    bg_gain_db=-17.0,
    duck_range_db=-4.0,
    duck_release_ms=1500.0,
    duck_lift_db=0.75,
    placeholder=(
        "[calm] The little cottage sat at the edge of a quiet wood.\n\n"
        "[soft] Lamplight spilled across the worn wooden floor, warm and golden.\n\n"
        "[warm] Outside, soft rain began to fall, steady and slow.\n\n"
        "[pause for 2 seconds]\n\n"
        "[calm] You settle deeper into the armchair, and the room grows still."
    ),
)

# ============================================================================
# Registry: keyed by .label for Streamlit selectbox integration
# ============================================================================
PRESETS: dict[str, ContentPreset] = {
    MEDITATION.label: MEDITATION,
    SLEEP_STORY.label: SLEEP_STORY,
}
"""Dict of all available content presets, keyed by display label.
Order matters: Meditation is first (default index 0 in selectbox)."""
