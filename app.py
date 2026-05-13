"""Streamlit UI for the meditation audio mixer."""
from __future__ import annotations

import datetime as dt
import traceback
from pathlib import Path

import streamlit as st
from elevenlabs.types import VoiceSettings

from meditation_mixer import cache, library, reverb, tts
from meditation_mixer.config import (
    CHUNK_MAX_CHARS_CONSERVATIVE,
    DEFAULT_MODEL_ID,
    DEFAULT_SEED,
    ELEVENLABS_API_KEY,
    FALLBACK_MODEL_ID,
    LRA_RANGE,
    OUTPUTS_DIR,
    TARGET_LUFS,
    TRUE_PEAK_DB,
)
from meditation_mixer.mixer import MixSettings, render

st.set_page_config(page_title="Meditation Mixer", page_icon="🧘", layout="wide")
st.title("Meditation Audio Mixer")
st.caption(
    "ElevenLabs v3 + Pedalboard. Clean voice path by default (no reverb / "
    "EQ / compression), frequency-selective ducking with look-ahead, "
    "4× true-peak limiter, LUFS-gated master."
)

if not ELEVENLABS_API_KEY:
    st.error(
        "`ELEVENLABS_API_KEY` is not set. Copy `.env.example` to `.env` and add your key, "
        "then restart the app."
    )
    st.stop()


@st.cache_data(ttl=600, show_spinner="Loading voices…")
def cached_voices() -> list[tuple[str, str]]:
    return [(v.voice_id, v.label) for v in tts.list_voices()]


# ---------------- Sidebar ---------------- #
with st.sidebar:
    st.header("Voice")
    try:
        voices = cached_voices()
    except Exception as e:
        st.error(f"Could not load voices: {e}")
        st.stop()

    voice_id = st.selectbox(
        "ElevenLabs voice",
        options=[v[0] for v in voices],
        format_func=lambda vid: next((label for vid_, label in voices if vid_ == vid), vid),
        help=(
            "Curated top 5 v3 meditation voices. Serena is a stock voice and "
            "always works; the others are voice-library voices — open each "
            "in elevenlabs.io/voice-library and click 'Add to my voices' "
            "before first use."
        ),
    )
    model_id = st.selectbox(
        "Model",
        options=[DEFAULT_MODEL_ID, FALLBACK_MODEL_ID, "eleven_turbo_v2_5"],
        index=0,
        help="v3 supports audio tags ([whispers], [breathes], [soft]). v2 is the stable fallback.",
    )
    output_format = st.selectbox("Output format", ["wav", "mp3"], index=0)

    st.subheader("Voice settings")
    stability_preset = st.radio(
        "Stability preset",
        options=list(tts.STABILITY_PRESETS.keys()),
        index=2,  # Meditative
        horizontal=True,
        help=(
            "Creative (0.30): most expressive, can drift on long sessions. "
            "Natural (0.50): balanced. "
            "Meditative (0.65): RECOMMENDED. Locks voice to prevent drift, honors tags. "
            "Robust (0.80): most stable but IGNORES [whispers]/[soft]/[breathes] tags."
        ),
    )
    stability_default = tts.STABILITY_PRESETS[stability_preset]
    stability = st.slider("Stability (fine-tune)", 0.0, 1.0, stability_default, 0.05,
                          help="≥0.75 makes v3 ignore audio tags; ≤0.40 may drift. "
                               "Research recommends 0.65–0.85 for meditation (Optimizations12 §2.3).")
    similarity = st.slider("Similarity boost", 0.0, 1.0, 0.80, 0.01,
                           help=("0.80 is the production default — acts as the acoustic "
                                 "anchor that locks the voice timbre across chunks. "
                                 "Research recommends 0.75–0.90 (§2.3). Values "
                                 "above ~0.80 introduce timbral artifacts (a "
                                 "zippery character on sibilants/breaths)."))
    style = st.slider("Style", 0.0, 1.0, 0.0, 0.05,
                      help="ElevenLabs and research (§2.3) recommend 0.0 for meditation.")
    speed = st.slider("Speed", 0.7, 1.2, 0.78, 0.01,
                      help=("0.78 is the default — pulls v3 toward ~95–110 WPM "
                            "calm meditation pacing. Research (§1.3) suggests "
                            "0.85–0.90 but that lands at ~130 WPM, too fast for "
                            "deep relaxation. Below 0.78 you start to hear "
                            "timbre warble; above 0.85 the voice drifts to 'narrator'."))
    pause_scale = st.slider("Pause scale", 0.5, 3.0, 2.0, 0.05,
                            help="Increased to 2.0 to give much slower, spacious pacing.")
    seed = st.number_input(
        "Seed", min_value=tts.SEED_MIN, max_value=tts.SEED_MAX,
        value=DEFAULT_SEED, step=1,
        help="Same seed + same text + same settings = identical audio. Drives the cache key.",
    )

    with st.expander("Advanced TTS"):
        tone_preset = st.text_input(
            "Tone preset (prepended at chunk boundaries)",
            value=tts.DEFAULT_TONE_PRESET,
            help=("Audio tag(s) to prepend at the START of every speech chunk that "
                  "doesn't already begin with a `[tag]`. v3 has no server-side "
                  "stitching, so this is the only continuity tool you have. Set to "
                  "blank to disable. Common values: `[soft][slowly]`, "
                  "`[calm][gently]`, `[whispers][softly]`."),
        )
        time_stretch_factor = st.slider(
            "Time-stretch factor (post-TTS)", 1.0, 1.4, 1.05, 0.01,
            help="Set to 1.05 to physically slow down the generated voice gently without pitching it down.",
        )
        chunk_lufs_target = st.slider(
            "Per-chunk LUFS target", -30.0, -10.0, -19.0, 0.5,
            help=("Normalize each rendered chunk to this integrated LUFS BEFORE "
                  "mixing. Fixes the 'this paragraph is louder than the next' "
                  "drift v3 produces. Set the value to -10 to disable."),
        )
        if chunk_lufs_target > -10.5:
            chunk_lufs_target = None  # the slider's "off" sentinel
        language_code_input = st.text_input(
            "Language code (ISO 639-1, optional)", value="",
            placeholder="e.g. en, es, fr, ja",
            help="Leave blank to let the model auto-detect. Set if you hear pronunciation slips.",
        )
        language_code = language_code_input.strip() or None
        normalization = st.selectbox(
            "Text normalization", options=["auto", "on", "off"], index=0,
            help="Controls how numbers, dates, abbreviations are spoken. 'auto' is almost always right.",
        )
        chunking_strategy = st.radio(
            "Chunking strategy",
            options=["Large (default)", "Conservative (research)"],
            index=0,
            horizontal=True,
            help=("Large (4400 chars): fewer chunk boundaries, less inter-chunk "
                  "drift — empirically validated default. "
                  "Conservative (800 chars): prevents intra-chunk attention decay "
                  "as recommended by Optimizations12 §2.2. Use if you experience "
                  "voice drift on very long (>15 min) meditations."),
        )
        max_chunk_chars = (
            CHUNK_MAX_CHARS_CONSERVATIVE
            if chunking_strategy.startswith("Conservative")
            else None  # None = use the default from config
        )

    st.divider()
    st.header("Mix")
    bg_gain_db = st.slider("Background gain (dB)", -30.0, 0.0, -11.0, 0.5)
    st.markdown("**Sidechain duck**")
    use_script_aware_duck = st.checkbox(
        "Script-aware (predictive + pause lift)",
        value=True,
        help=("Builds a deterministic gain curve from phrase timestamps: "
              "descends 300 ms BEFORE each phrase, holds -9 dB during, "
              "releases over 700 ms, LIFTS the music +1.5 dB during long "
              "pauses. Combined with the reactive detector via min-gain "
              "as a safety net for off-script audio. Makes the bed 'breathe' "
              "with the voice."),
    )
    duck_range_db = st.slider("Duck range (dB)", -24.0, 0.0, -7.0, 0.5,
                              help="Maximum dip. -9 dB sounds like Calm/Headspace.")
    duck_release_ms = st.slider("Duck release (ms)", 50.0, 2500.0, 1000.0, 25.0,
                                help=("1000 ms aligns with research (§3.2) lower bound for languid, "
                                      "cinematic music swell-back. 700 ms feels like 'breathing'; "
                                      "1500–2000 ms for extra spacious mixes."))
    duck_lookahead_ms = st.slider("Duck look-ahead (ms)", 0.0, 30.0, 10.0, 1.0,
                                  help="Reactive detector look-ahead. Script-aware duck has its own 300 ms predictive descent.")
    duck_lift_db = st.slider("Pause lift (dB)", 0.0, 4.0, 2.0, 0.25,
                             help="Music lift during pauses ≥ 1.5 s. +1.5 dB is conservative; >+3 dB starts to sound like 'rising' rather than 'breathing'.")

    st.markdown("**Music pocket EQ (static)**")
    music_pocket_db = st.slider("Pocket cut (dB @ 2 kHz)", -6.0, 0.0, -2.0, 0.25,
                                help=("Permanent 2 kHz dip in the music bed so the "
                                      "speech intelligibility band is always clear. "
                                      "Lets dynamic ducking be gentler."))

    st.markdown("**Music brightness (high-shelf boost)**")
    st.caption(
        "Compensates for Fletcher-Munson brightness loss when ducking "
        "attenuates overall volume. The ear loses high-freq sensitivity "
        "faster than midrange as amplitude drops. (Ref: Optimizations12 §3.3)"
    )
    music_treble_db = st.slider("Treble boost (dB)", 0.0, 6.0, 3.0, 0.5,
                                help="+3 dB at 4.5 kHz keeps the music ethereal even when heavily ducked. 0 = bypass.")
    music_treble_freq_hz = st.slider("Treble freq (Hz)", 3000.0, 6000.0, 4500.0, 100.0,
                                     help="High-shelf cutoff. 4000–5000 Hz bypasses the fundamental voice band (200–3000 Hz).")

    st.markdown("**Voice processing (off by default — clean ElevenLabs output)**")
    st.caption(
        "All voice post-processing is disabled by default. The previous "
        "defaults (plate reverb + presence/air EQ + compression) added an "
        "'echoey/robotic' character on close-mic'd TTS. Leave these off "
        "for the cleanest, most natural voice."
    )
    apply_voice_reverb = st.checkbox(
        "Apply convolution reverb on voice", value=False,
        help="Plate reverb send. Off by default to keep the voice clean and crisp.",
    )
    apply_voice_compression = st.checkbox(
        "Apply voice compression", value=False,
        help="Vocal compressor (-22 dB threshold, 2.5:1). Adds a 'broadcast/podcast' polish — off by default.",
    )
    apply_voice_deess = st.checkbox(
        "Apply de-esser", value=False,
        help="Reduces sibilance. ElevenLabs v3 voices are clean enough that this usually just makes the voice less crisp.",
    )
    presence_db = st.slider("Presence (+dB @ 4 kHz)", -3.0, 6.0, 0.0, 0.5,
                            help="0 = bypass. Adds a forward/intimate character at the cost of naturalness.")
    air_db = st.slider("Air (+dB @ 10 kHz shelf)", -3.0, 6.0, 0.0, 0.5,
                       help="0 = bypass. Adds 'sparkle' — usually unnecessary on v3.")
    reverb_wet_db = st.slider("Reverb wet (dB)", -40.0, -6.0, -20.0, 0.5,
                              help="Only used when 'Apply convolution reverb on voice' is on.")
    reverb_duck_db = st.slider("Reverb duck during voice (dB)", -12.0, 0.0, -6.0, 0.5,
                               help="Cut the voice reverb wet while voice is speaking so consonants stay clear.")
    reverb_lift_db = st.slider("Reverb lift during pauses (dB)", 0.0, 9.0, 4.0, 0.5,
                               help="Boost the wet during long pauses so the tail blooms into the silence — the 'spacious room' cue.")

    st.divider()
    st.header("Arrangement")
    pre_roll_s = st.slider("Pre-roll (s)", 0.0, 15.0, 3.0, 0.5)
    post_roll_s = st.slider("Post-roll (s)", 0.0, 30.0, 5.0, 0.5)

    st.divider()
    if st.button("Clear TTS cache", help="Remove all cached ElevenLabs chunks."):
        n = cache.clear()
        st.success(f"Cleared {n} cache files.")


# ---------------- Main ---------------- #
left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader("Script")
    with st.expander("Format & audio tag reference"):
        st.markdown(
            "**Paste a script generated using `SCRIPT_GUIDE.md`.** "
            "Give that file to Claude/Gemini/etc. and paste the result here.\n\n"
            "**Quick rules:**\n"
            "- Paragraphs (blank line between) become TTS chunks.\n"
            "- `### PAUSE 5s` on its own line = exact silence (free, no API cost).\n"
            "- Tone tags belong at the **start** of each paragraph: "
            "`[soft]`, `[whispers]`, `[gently]`, `[calm]`, `[serene]`, `[warmly]`.\n"
            "- Mid-line action tags: `[exhales]`, `[inhales]`, `[breathes]`, `[sighs]`, `[pauses]`.\n"
            "- Ellipses (`…`) = short hesitation pause. Em-dash (`—`) = stronger pause.\n"
            "- Stability must be **Natural (0.50)** or lower for audio tags to work."
        )
    lyrics = st.text_area(
        "Meditation script",
        height=320,
        placeholder=(
            "[soft] Welcome.  Find a comfortable position…\n"
            "and when you're ready, [breathes] gently close your eyes.\n\n"
            "### PAUSE 5s\n\n"
            "[whispers] Take a slow breath in… [inhales]\n"
            "…and let it go. [exhales]"
        ),
        label_visibility="collapsed",
    )

with right:
    st.subheader("Background")
    uploaded = st.file_uploader(
        "Upload royalty-free background sound",
        type=["wav", "mp3", "flac", "ogg", "m4a", "aiff", "aif"],
        accept_multiple_files=False,
    )
    if uploaded is not None:
        saved_path = library.save_upload(uploaded.name, uploaded.getvalue())
        st.success(f"Saved → `{saved_path.name}`")

    backgrounds = library.list_backgrounds()
    if not backgrounds:
        st.info("No background tracks yet. Upload one above to get started.")
        bg_path = None
    else:
        bg_path_str = st.selectbox(
            "Choose background",
            options=[str(p) for p in backgrounds],
            format_func=lambda s: Path(s).name,
        )
        bg_path = Path(bg_path_str)
        with open(bg_path, "rb") as f:
            st.audio(f.read(), format=f"audio/{bg_path.suffix.lstrip('.')}")

    st.subheader("Reverb IR")
    reverb.ensure_default_ir()
    irs = reverb.list_irs()
    ir_path_str = st.selectbox(
        "Impulse response",
        options=[str(p) for p in irs],
        format_func=lambda s: Path(s).name,
        help="Synthetic plate is the default. Drop your own IR file into `irs/` to use a real room/plate.",
    )
    reverb_ir_path = Path(ir_path_str) if ir_path_str else None


st.divider()
disabled = not (lyrics.strip() and voice_id and bg_path is not None)
render_clicked = st.button("Render meditation", type="primary", disabled=disabled,
                           use_container_width=True)

if render_clicked:
    voice_settings = VoiceSettings(
        stability=stability,
        similarity_boost=similarity,
        style=style,
        speed=speed,
        use_speaker_boost=False,
    )

    settings = MixSettings(
        bg_gain_db=bg_gain_db,
        duck_range_db=duck_range_db,
        duck_release_ms=duck_release_ms,
        duck_lookahead_ms=duck_lookahead_ms,
        use_script_aware_duck=use_script_aware_duck,
        duck_lift_db=duck_lift_db,
        music_pocket_db=music_pocket_db,
        music_treble_db=music_treble_db,
        music_treble_freq_hz=music_treble_freq_hz,
        pre_roll_s=pre_roll_s,
        post_roll_s=post_roll_s,
        apply_voice_reverb=apply_voice_reverb,
        apply_voice_compression=apply_voice_compression,
        apply_voice_deess=apply_voice_deess,
        reverb_wet_db=reverb_wet_db,
        reverb_duck_db=reverb_duck_db,
        reverb_lift_db=reverb_lift_db,
        reverb_ir_path=reverb_ir_path,
        presence_db=presence_db,
        air_db=air_db,
    )

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUTS_DIR / f"meditation_{timestamp}.{output_format}"

    progress = st.progress(0, text="Preparing…")
    try:
        def tts_progress(i, total, msg):
            pct = int(5 + 60 * (i / max(total, 1)))
            progress.progress(min(pct, 65), text=f"TTS: {msg}")

        voice, sr, tts_manifest = tts.synthesize_script(
            lyrics,
            voice_id=voice_id,
            model_id=model_id,
            settings=voice_settings,
            seed=int(seed),
            language_code=language_code,
            apply_text_normalization=normalization,
            progress=tts_progress,
            pause_scale=pause_scale,
            tone_preset=(tone_preset or None),
            time_stretch_factor=float(time_stretch_factor),
            normalize_chunk_lufs=chunk_lufs_target,
            max_chunk_chars=max_chunk_chars,
        )
        progress.progress(70, text="Mixing voice + background…")

        manifest = render(
            voice, sr, bg_path, settings, out_path,
            output_format=output_format,
            speech_segments=tts_manifest.get("speech_segments"),
        )
        progress.progress(100, text="Done.")
    except Exception as e:
        progress.empty()
        st.error(f"Render failed: {e}")
        st.code(traceback.format_exc())
        st.stop()

    tts_warnings = tts_manifest.get("warnings") or []
    if stability >= 0.75 and "[" in lyrics:
        tts_warnings.append(
            f"Stability {stability:.2f} is in the Robust range — v3 ignores audio tags "
            "above ~0.75. Drop to 0.50 (Natural) if [whispers]/[breathes]/[soft] are not landing."
        )
    for w in tts_warnings:
        st.warning(w)

    issues = manifest.get("issues") or []
    if issues:
        st.warning("Master verification flagged issues — review before shipping.")
        for issue in issues:
            st.write(f"• {issue}")
    else:
        st.success(
            f"✓ Mastered to {manifest['integrated_lufs']:+.2f} LUFS / "
            f"{manifest['true_peak_db']:+.2f} dBTP / "
            f"LRA {manifest['lra_lu']:.1f} LU"
        )

    cols = st.columns(4)
    cols[0].metric("Integrated LUFS", f"{manifest['integrated_lufs']:+.2f}", help=f"target {TARGET_LUFS:+.1f}")
    cols[1].metric("True peak (dBTP)", f"{manifest['true_peak_db']:+.2f}", help=f"target ≤ {TRUE_PEAK_DB:+.1f}")
    cols[2].metric("LRA (LU)", f"{manifest['lra_lu']:.1f}", help=f"target {LRA_RANGE[0]:.0f}-{LRA_RANGE[1]:.0f}")
    cols[3].metric("Duration", f"{manifest['duration_s']:.1f}s")

    st.info(f"🎵 {manifest['bg_fit_note']}")

    st.caption(
        f"TTS: {tts_manifest['speech_chunks']} chunks, "
        f"{tts_manifest['cache_hits']} cached + {tts_manifest['cache_misses']} new, "
        f"{tts_manifest['total_chars']} chars · "
        f"Stems → `{Path(manifest['stems_dir']).name}/`"
        if manifest.get("stems_dir") else
        f"TTS: {tts_manifest['speech_chunks']} chunks, "
        f"{tts_manifest['cache_hits']} cached + {tts_manifest['cache_misses']} new"
    )

    with open(out_path, "rb") as f:
        audio_bytes = f.read()
    st.audio(audio_bytes, format=f"audio/{output_format}")
    st.download_button(
        "Download",
        data=audio_bytes,
        file_name=out_path.name,
        mime=f"audio/{output_format}",
        use_container_width=True,
    )
