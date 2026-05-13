"""ElevenLabs text-to-speech wrapper, tuned for v3 and meditation content.

Default model: `eleven_v3`. v3 supports inline audio tags ([whispers],
[breathes], [soft], [exhales], etc.) which v2 ignores entirely. We default
stability to 0.5 ("Natural") because >= 0.75 ("Robust") makes the model
ignore audio tags, and < 0.4 ("Creative") drifts over long sessions.

Chunking: paragraph-based, target 800-1500 chars per chunk, hard ceiling
4500 chars (v3's per-request limit is 5000). We sit at the top of that
window on purpose: each boundary is a place where prosody/timbre can
drift, so fewer chunks = less drift on long meditations. For non-v3
models we also send `previous_text` / `next_text` for continuity; v3
rejects those params, so on v3 we rely on a fixed `seed` plus
similarity_boost as the timbre anchor. Decoded PCM is stitched with a 30 ms equal-power crossfade so the
joins between chunks (and between chunks and `### PAUSE` silence) have no
audible click or "blank static" tick.

Long pauses are programmatic silence concatenated between chunks, NOT
`<break>` tags or `[long pause]` repetitions. v2's `<break>` caps at 3 s and
both ElevenLabs and the model itself warn that excessive pause tags cause
speed-ups and artifacts.
"""
from __future__ import annotations

import io
import re
import warnings
from dataclasses import dataclass
from typing import Iterable, Literal

import numpy as np
from elevenlabs.client import ElevenLabs
from elevenlabs.types import VoiceSettings

from . import cache
from .chunker import HARD_MAX_CHARS, PauseChunk, SpeechChunk, chunk_script, neighbors
from .config import (
    DEFAULT_MODEL_ID,
    DEFAULT_SEED,
    ELEVENLABS_API_KEY,
    SAMPLE_RATE,
)

# v3 seed range per the official API reference.
SEED_MIN = 0
SEED_MAX = 4_294_967_295

# Per-chunk character bounds. v3 is unreliable below ~250 chars and the API
# hard-caps at 5000. We aim for 800-1200 with a 4500 ceiling.
CHUNK_MIN_FOR_RELIABILITY = 250

# Meditation defaults, tuned per the production-quality research plan:
#  - stability 0.55 — slightly above "Natural" (0.50). Audio tags still
#    respond (the >=0.75 "Robust" threshold ignores them); the extra 0.05
#    damps prosody jitter on long meditations without flattening tags.
#  - similarity_boost 0.78 — practitioner consensus is that values above
#    ~0.80 introduce timbral artifacts (a brittle/zippery character on
#    sibilants and breaths). 0.78 sits just below that threshold and
#    delivers cleaner cross-chunk timbre than the previous 0.92 setting,
#    even without server-side stitching.
#  - style 0.0 — ElevenLabs explicitly recommends 0.0 for meditation;
#    higher adds caricature.
#  - speed 0.88 — mild model-level slowdown, leaving room for a
#    Rubber Band R3 post-stretch (~1.18x length) to reach the Tamara
#    Levitt / Andy Puddicombe 95-110 WPM range. v3's `speed` slider is a
#    weak lever on its own; ElevenLabs' own v3 best-practices doc says
#    "speed is also controlled through audio tags" and warns that 0.7-0.8
#    can introduce timbre warble. Splitting slowdown across speed + post-
#    stretch keeps each stage in its quality-safe band.
#  - speaker_boost True — slightly improves perceived similarity to the
#    original voice on long-form content; cost-free.
MEDITATION_VOICE_SETTINGS = VoiceSettings(
    stability=0.55,
    similarity_boost=0.78,
    style=0.0,
    speed=0.88,
    use_speaker_boost=True,
)


# Default tone preset prepended to speech chunks that don't already begin
# with an audio tag. Reasserting calming tags at every chunk boundary is
# the only continuity tool v3 exposes (no prev/next_text, no request_id
# stitching), so this is the single biggest fix for "prosody flattens
# over time" drift on long meditations.
DEFAULT_TONE_PRESET = "[soft][slowly]"

# Named presets matching ElevenLabs' v3 mode labels.
STABILITY_PRESETS: dict[str, float] = {
    "Creative": 0.30,   # most expressive, can drift
    "Natural": 0.50,    # balanced, audio tags work — RECOMMENDED
    "Robust": 0.80,     # most stable, IGNORES audio tags
}


@dataclass(frozen=True)
class Voice:
    voice_id: str
    name: str
    category: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} ({self.category})" if self.category else self.name


# Curated top 5 ElevenLabs v3 voices for meditation, selected from ElevenLabs'
# official meditation collection (elevenlabs.io/voice-library/meditation),
# third-party reviews (nerdynav.com, json2video catalog), and the voice
# previously recommended in this project. All five work with `eleven_v3` and
# respond correctly to audio tags ([whispers], [breathes], [soft]) at the
# Natural stability preset.
#
# NOTE: Only Serena is a stock voice (always usable). The other four are
# community voice-library voices — to use them via the API, open each in the
# ElevenLabs voice library and click "Add to my voices" first.
MEDITATION_VOICES: list[Voice] = [
    Voice(
        voice_id="pMsXgVXv3BLzUgSXRplE",
        name="Serena — Warm & Meditative",
        category="female · stock",
    ),
    Voice(
        voice_id="zA6D7RyKdc2EClouEMkP",
        name="AImee — ASMR & Meditation",
        category="female · soft whisper",
    ),
    Voice(
        voice_id="WuBPEavIaQB56EnsGvFh",
        name="Eryn — Therapist & Meditation",
        category="female · calm therapist",
    ),
    Voice(
        voice_id="wgHvco1wiREKN0BdyVx5",
        name="Drew — Deep, Soothing Guided Meditation",
        category="male · deep",
    ),
    Voice(
        voice_id="xGDJhCwcqw94ypljc95Z",
        name="Archer — Guided Meditation & Narration",
        category="male · narration",
    ),
]


def _client() -> ElevenLabs:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return ElevenLabs(api_key=ELEVENLABS_API_KEY)


def list_voices() -> list[Voice]:
    """Return the curated top 5 meditation voices for ElevenLabs v3."""
    return list(MEDITATION_VOICES)


def _pcm_to_float(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


# Detect a leading audio tag run at the start of a chunk. We treat ALL
# leading bracketed tags as "the user already specified a tone", so we
# don't double-tag chunks the script-writer was opinionated about.
_LEADING_TAG_RE = re.compile(r"^\s*(?:\[[^\[\]\n]{1,30}\]\s*){1,4}")


def _apply_tone_preset(text: str, tone_preset: str | None) -> str:
    """Prepend `tone_preset` to a chunk only if it doesn't already start
    with an audio tag. Cheap continuity anchor for v3 which has no
    server-side stitching: each chunk gets a fresh tonal nudge.
    """
    if not tone_preset:
        return text
    preset = tone_preset.strip()
    if not preset:
        return text
    if _LEADING_TAG_RE.match(text):
        return text  # user already specified tone for this chunk
    return f"{preset} {text.lstrip()}"


def _time_stretch_mono(y: np.ndarray, sr: int, length_factor: float) -> np.ndarray:
    """Rubber Band R3 time-stretch a mono float32 signal by `length_factor`.

    `length_factor > 1.0` LENGTHENS the audio (slows down) without
    altering pitch — e.g. 1.18 = 18 % longer. We pass `preserve_formants
    =True` so the voice timbre stays intact (no chipmunking) and use the
    long-FFT-window + smooth-transient settings recommended for speech.

    Note: pedalboard's `stretch_factor` is a SPEED multiplier, the
    inverse of what we want. We invert here so callers think in
    "length-stretch" units.
    """
    if length_factor is None or abs(length_factor - 1.0) < 1e-3:
        return y
    if length_factor <= 0:
        raise ValueError(f"length_factor must be > 0, got {length_factor}")

    # Defer import so callers that don't stretch don't pay the cost.
    from pedalboard import time_stretch as _ts

    speed_factor = 1.0 / float(length_factor)
    y32 = y.astype(np.float32, copy=False)
    stretched = _ts(
        y32, float(sr),
        stretch_factor=speed_factor,
        pitch_shift_in_semitones=0.0,
        high_quality=True,
        transient_mode="smooth",        # smoother on sustained vowels
        transient_detector="compound",
        retain_phase_continuity=True,
        use_long_fft_window=True,       # smoother on speech
        use_time_domain_smoothing=False,
        preserve_formants=True,         # critical — keeps voice timbre
    )
    # pedalboard always returns (channels, samples). Squeeze to 1D.
    if stretched.ndim == 2:
        stretched = stretched[0]
    return stretched.astype(np.float32, copy=False)


def _normalize_chunk_lufs(
    y: np.ndarray, sr: int, target_lufs: float,
    silence_gate_lufs: float = -50.0,
) -> np.ndarray:
    """Per-chunk integrated-loudness normalization. Eliminates the
    "this paragraph is louder than the next one" drift that v3 produces
    across long sessions, before crossfading and mixing run.

    Falls back to a passthrough on chunks that are too short for a valid
    BS.1770 integrated measurement (<400 ms) or that are effectively
    silent (e.g. a chunk that was almost entirely breath). Both edge cases
    return the raw chunk so we never amplify near-silence into noise.
    """
    if y.size < int(sr * 0.4):
        return y
    try:
        import pyloudnorm as pyln
    except Exception:
        return y

    meter = pyln.Meter(sr, filter_class="DeMan")
    # pyloudnorm wants (samples, channels) for stereo and (samples,) for mono.
    measured = float(meter.integrated_loudness(y.astype(np.float32)))
    if not np.isfinite(measured) or measured < silence_gate_lufs:
        return y
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Possible clipped samples in output.",
            category=UserWarning,
            module=r"pyloudnorm\..*",
        )
        out = pyln.normalize.loudness(y.astype(np.float32), measured, target_lufs)
    return out.astype(np.float32, copy=False)


# Crossfade length when stitching consecutive TTS chunks (and pause silence)
# together. ElevenLabs v3 returns each chunk with a few ms of attack/release
# at the edges plus occasional tiny edge clicks; a short equal-power
# crossfade absorbs those without smearing speech. 30 ms is well under the
# duration of any phoneme (so intelligibility is untouched) but long enough
# to swallow the artifacts.
_CHUNK_XFADE_MS = 30.0


def _stitch_pieces(pieces: list[np.ndarray], sr: int,
                   xfade_ms: float = _CHUNK_XFADE_MS) -> np.ndarray:
    """Concatenate decoded chunk + pause arrays with an equal-power crossfade
    at every join.

    Why crossfade instead of `np.concatenate`:
      * Even seed-stable v3 chunks differ by a few ms of leading/trailing
        silence and the very first/last sample of each chunk can have a
        small DC step relative to the next chunk. Hard concat leaves an
        audible micro-click ("blank static" tick) at every boundary.
      * Silence-to-speech and speech-to-silence joins (around `### PAUSE`)
        get a gentle fade in/out for free, which sounds more natural than
        an abrupt cut.

    The fade is equal-power (cos/sin), so two uncorrelated signals (which
    is what adjacent v3 chunks are) sum to constant perceived loudness
    across the join.
    """
    if not pieces:
        return np.zeros(0, dtype=np.float32)
    if len(pieces) == 1:
        return pieces[0].astype(np.float32, copy=False)

    xfade_n = max(1, int(sr * xfade_ms / 1000.0))
    # Pre-compute the half-cycle equal-power curves once.
    t = np.linspace(0.0, 1.0, xfade_n, endpoint=False, dtype=np.float32)
    fade_out = np.cos(t * np.pi / 2.0).astype(np.float32)
    fade_in = np.sin(t * np.pi / 2.0).astype(np.float32)

    out = pieces[0].astype(np.float32, copy=True)
    for nxt in pieces[1:]:
        nxt = nxt.astype(np.float32, copy=False)
        n = min(xfade_n, out.shape[0], nxt.shape[0])
        if n <= 1:
            # One side is too short for a meaningful crossfade — fall back
            # to a hard concat. (Only happens for sub-millisecond pauses.)
            out = np.concatenate([out, nxt])
            continue
        if n < xfade_n:
            # Rebuild the curves at the shorter length.
            tt = np.linspace(0.0, 1.0, n, endpoint=False, dtype=np.float32)
            fo = np.cos(tt * np.pi / 2.0).astype(np.float32)
            fi = np.sin(tt * np.pi / 2.0).astype(np.float32)
        else:
            fo, fi = fade_out, fade_in
        head = out[:-n]
        cross = out[-n:] * fo + nxt[:n] * fi
        tail = nxt[n:]
        out = np.concatenate([head, cross, tail])
    return out


def _stitch_pieces_with_spans(
    pieces: list[np.ndarray], sr: int,
    xfade_ms: float = _CHUNK_XFADE_MS,
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Same as `_stitch_pieces`, but also returns each piece's (start, end)
    sample span in the stitched output. The span midpoint sits inside the
    piece's body — crossfade regions belong half to each neighbour, so we
    record each piece as [body_start, body_end_excl_xfade_into_next].

    Used by `synthesize_script` to surface phrase timestamps for script-
    aware ducking downstream.
    """
    if not pieces:
        return np.zeros(0, dtype=np.float32), []
    if len(pieces) == 1:
        y = pieces[0].astype(np.float32, copy=False)
        return y, [(0, y.shape[0])]

    xfade_n = max(1, int(sr * xfade_ms / 1000.0))
    spans: list[tuple[int, int]] = []
    out = pieces[0].astype(np.float32, copy=True)
    cursor = out.shape[0]
    spans.append((0, cursor))  # tentative; we'll trim the tail by xfade as we go

    t = np.linspace(0.0, 1.0, xfade_n, endpoint=False, dtype=np.float32)
    fade_out_c = np.cos(t * np.pi / 2.0).astype(np.float32)
    fade_in_c = np.sin(t * np.pi / 2.0).astype(np.float32)

    for nxt in pieces[1:]:
        nxt = nxt.astype(np.float32, copy=False)
        n = min(xfade_n, out.shape[0], nxt.shape[0])
        if n <= 1:
            start = out.shape[0]
            out = np.concatenate([out, nxt])
            spans.append((start, start + nxt.shape[0]))
            continue
        if n < xfade_n:
            tt = np.linspace(0.0, 1.0, n, endpoint=False, dtype=np.float32)
            fo = np.cos(tt * np.pi / 2.0).astype(np.float32)
            fi = np.sin(tt * np.pi / 2.0).astype(np.float32)
        else:
            fo, fi = fade_out_c, fade_in_c

        head = out[:-n]
        cross = out[-n:] * fo + nxt[:n] * fi
        tail = nxt[n:]
        new_out = np.concatenate([head, cross, tail])

        # The previous piece's body ends where the crossfade starts (out.shape[0] - n).
        # The new piece's body starts at the END of the crossfade (out.shape[0]).
        prev_start, _ = spans[-1]
        spans[-1] = (prev_start, out.shape[0] - n)
        new_start = out.shape[0]
        new_end = new_out.shape[0]
        spans.append((new_start, new_end))
        out = new_out

    return out, spans


def _settings_dict(s: VoiceSettings) -> dict:
    return {
        "stability": s.stability,
        "similarity_boost": s.similarity_boost,
        "style": s.style,
        "speed": s.speed,
        "use_speaker_boost": s.use_speaker_boost,
    }


def _clamp_seed(seed: int) -> int:
    return max(SEED_MIN, min(SEED_MAX, int(seed)))


def _extract_request_id(headers: dict[str, str]) -> str | None:
    """Pull the ElevenLabs request id out of response headers. Different
    deployments expose it under slightly different keys, so check the
    common ones in priority order.
    """
    for key in ("request-id", "x-request-id", "x-trace-id"):
        rid = headers.get(key)
        if rid:
            return rid
    return None


def _render_one_chunk(
    text: str,
    voice_id: str,
    model_id: str,
    settings: VoiceSettings,
    seed: int,
    previous_text: str | None,
    next_text: str | None,
    language_code: str | None,
    apply_text_normalization: Literal["auto", "on", "off"],
    previous_request_ids: list[str] | None = None,
) -> tuple[bytes, str | None]:
    """Render one chunk. Returns (pcm_bytes, request_id_or_None).

    The request_id is captured from the response headers for non-v3 models
    that accept `previous_request_ids` as a continuity hint. v3 rejects
    both prev/next_text and prev/next_request_ids, so on v3 the captured
    id is informational only (useful for logs/debugging) and is NOT sent
    back as a stitching parameter.
    """
    if len(text) > HARD_MAX_CHARS:
        raise ValueError(
            f"Chunk has {len(text)} chars; max is {HARD_MAX_CHARS}. "
            "This is a chunker bug — please report."
        )

    # Cache key intentionally OMITS `previous_request_ids`. Those depend on
    # render-time state (which chunks happened to be re-rendered vs cache
    # hits) and would invalidate the cache on every run. The audio for a
    # given chunk text + seed + voice settings is reproducible enough that
    # treating the request_id chain as a render-time hint, not a cache key,
    # keeps caching useful without compromising correctness.
    payload = {
        "text": text,
        "voice_id": voice_id,
        "model_id": model_id,
        "voice_settings": _settings_dict(settings),
        "output_format": "pcm_48000",
        "seed": seed,
        "previous_text": previous_text,
        "next_text": next_text,
        "language_code": language_code,
        "apply_text_normalization": apply_text_normalization,
    }
    cached = cache.load(payload)
    if cached is not None:
        # Cache hit — no fresh request_id. The next chunk will simply have
        # one fewer continuity anchor; v3 accepts up to 3 prev request_ids
        # so the chain stays useful as long as *some* chunks render fresh.
        return cached, _load_cached_request_id(payload)

    api_kwargs = dict(
        text=text,
        voice_id=voice_id,
        model_id=model_id,
        output_format="pcm_48000",
        voice_settings=settings,
        seed=seed,
        apply_text_normalization=apply_text_normalization,
    )
    # `eleven_v3` rejects BOTH continuity hints — previous_text/next_text
    # AND previous_request_ids/next_request_ids — with a 400. So on v3
    # there is currently no server-side stitching available; the only
    # cross-chunk anchors are the fixed seed and similarity_boost. For
    # other models (v2/turbo) prev/next_text is still supported and used.
    if model_id != "eleven_v3":
        api_kwargs["previous_text"] = previous_text
        api_kwargs["next_text"] = next_text
        if previous_request_ids:
            api_kwargs["previous_request_ids"] = list(previous_request_ids)[-3:]
    if language_code:
        api_kwargs["language_code"] = language_code

    # Use `with_raw_response` so we can read the response headers and pull
    # the request_id for stitching the next chunk.
    raw = _client().text_to_speech.with_raw_response
    with raw.convert(**api_kwargs) as resp:
        request_id = _extract_request_id(resp.headers)
        buf = io.BytesIO()
        for chunk in resp.data:
            if chunk:
                buf.write(chunk)
    pcm = buf.getvalue()
    if not pcm:
        raise RuntimeError("ElevenLabs returned no audio data.")
    cache.store(payload, pcm)
    if request_id:
        _store_cached_request_id(payload, request_id)
    return pcm, request_id


def _request_id_sidecar(payload: dict):
    return cache.cache_path(payload).with_suffix(".rid")


def _load_cached_request_id(payload: dict) -> str | None:
    p = _request_id_sidecar(payload)
    if p.exists():
        try:
            return p.read_text().strip() or None
        except OSError:
            return None
    return None


def _store_cached_request_id(payload: dict, request_id: str) -> None:
    try:
        _request_id_sidecar(payload).write_text(request_id)
    except OSError:
        pass


def synthesize_script(
    script: str,
    voice_id: str,
    model_id: str = DEFAULT_MODEL_ID,
    settings: VoiceSettings = MEDITATION_VOICE_SETTINGS,
    seed: int = DEFAULT_SEED,
    language_code: str | None = None,
    apply_text_normalization: Literal["auto", "on", "off"] = "auto",
    progress: callable | None = None,
    pause_scale: float = 1.0,
    tone_preset: str | None = DEFAULT_TONE_PRESET,
    time_stretch_factor: float = 1.18,
    normalize_chunk_lufs: float | None = -19.0,
) -> tuple[np.ndarray, int, dict]:
    """Render a full meditation script.

    Splits into TTS chunks + programmatic pauses, synthesizes each TTS
    chunk with continuity hints where the model supports them (prev/next
    text + prev_request_ids for v2/turbo; v3 has neither and relies on
    seed + similarity_boost only), then per-chunk runs:

      1. Tone-tag reassertion — prepend `tone_preset` (default
         `[soft][slowly]`) to any chunk that doesn't already start with
         an audio tag. The only continuity anchor v3 exposes is the
         prompt itself; reasserting tags at every chunk boundary is what
         keeps a 20-minute meditation from drifting into "audiobook
         narrator" tone by chunk 8.
      2. Per-chunk LUFS normalization (if `normalize_chunk_lufs` is
         not None) — eliminates the cross-chunk loudness drift v3
         produces under any settings.
      3. Rubber Band R3 time-stretch (if `time_stretch_factor` > 1.0,
         default 1.18) — pulls pace from v3's typical ~150 WPM down to
         the Tamara Levitt / Andy Puddicombe ~95-110 WPM band without
         pitch artifacts. PauseChunk silences are NOT stretched (their
         durations are already explicit in the script).

    Pieces are then concatenated with equal-power crossfades.

    Returns: (samples, sample_rate, manifest_dict). Manifest includes
    `speech_segments` — a list of (start_s, end_s) tuples covering each
    rendered speech chunk in the final timeline. The mixer uses these for
    deterministic, script-aware ducking.
    """
    if not script.strip():
        raise ValueError("Cannot synthesize empty script.")

    seed = _clamp_seed(seed)

    parts = chunk_script(script, pause_scale=pause_scale)
    if not parts:
        raise ValueError("Script produced no chunks after parsing.")

    speech_chunks = [c for c in parts if isinstance(c, SpeechChunk)]
    if not speech_chunks:
        raise ValueError("Script contains no speech, only pauses.")

    # Warn (not fail) on chunks that are too short — v3 needs context to
    # stabilize.
    short_chunks = [c for c in speech_chunks if len(c.text) < CHUNK_MIN_FOR_RELIABILITY]

    ctx = neighbors(parts)
    speech_idx = 0
    pieces: list[np.ndarray] = []
    # Track (kind, start_sample, end_sample) for each piece so we can
    # build per-piece timestamps in the stitched output below.
    piece_kinds: list[str] = []   # "speech" or "pause"
    cache_hits = 0
    cache_misses = 0
    total_chars = 0
    # Rolling window of the last few request_ids; threaded into each new
    # render as `previous_request_ids`. v3 accepts up to 3, so we cap here.
    recent_request_ids: list[str] = []

    for i, part in enumerate(parts):
        if isinstance(part, PauseChunk):
            n = int(round(part.seconds * SAMPLE_RATE))
            pieces.append(np.zeros(n, dtype=np.float32))
            piece_kinds.append("pause")
            if progress:
                progress(i + 1, len(parts), f"silence {part.seconds:.1f}s")
            continue

        prev_t, next_t = ctx[speech_idx]
        speech_idx += 1
        # Apply tone-tag reassertion before the API call so the cache key
        # reflects the actual rendered text. User-tagged chunks pass
        # through untouched.
        rendered_text = _apply_tone_preset(part.text, tone_preset)
        total_chars += len(rendered_text)

        payload = {
            "text": rendered_text,
            "voice_id": voice_id,
            "model_id": model_id,
            "voice_settings": _settings_dict(settings),
            "output_format": "pcm_48000",
            "seed": seed,
            "previous_text": prev_t,
            "next_text": next_t,
            "language_code": language_code,
            "apply_text_normalization": apply_text_normalization,
        }
        is_hit = cache.cache_path(payload).exists()
        if is_hit:
            cache_hits += 1
        else:
            cache_misses += 1
        if progress:
            progress(i + 1, len(parts),
                     f"chunk {speech_idx}/{len(speech_chunks)} "
                     f"({'cached' if is_hit else 'new'}, {len(rendered_text)} chars)")

        pcm, request_id = _render_one_chunk(
            text=rendered_text,
            voice_id=voice_id,
            model_id=model_id,
            settings=settings,
            seed=seed,
            previous_text=prev_t,
            next_text=next_t,
            language_code=language_code,
            apply_text_normalization=apply_text_normalization,
            previous_request_ids=recent_request_ids,
        )
        if request_id:
            recent_request_ids.append(request_id)
            recent_request_ids = recent_request_ids[-3:]

        y = _pcm_to_float(pcm)

        # Per-chunk normalization BEFORE time-stretch: a clean LUFS
        # measurement on the un-stretched signal is cheaper and more
        # stable than measuring after stretching introduces sub-perceptual
        # artifacts.
        if normalize_chunk_lufs is not None:
            y = _normalize_chunk_lufs(y, SAMPLE_RATE, float(normalize_chunk_lufs))

        # Rubber Band R3 lengthening. Cumulative slowdown with the v3
        # `speed` setting brings ~150 WPM v3 output down to ~110 WPM.
        if time_stretch_factor and time_stretch_factor > 1.001:
            y = _time_stretch_mono(y, SAMPLE_RATE, float(time_stretch_factor))

        pieces.append(y)
        piece_kinds.append("speech")

    # Equal-power crossfade between every adjacent piece (speech↔speech,
    # speech↔pause, pause↔speech). Eliminates the boundary clicks/drops
    # that hard concatenation can leave behind, and gives PAUSE markers a
    # smooth fade in/out for free.
    samples, piece_spans = _stitch_pieces_with_spans(pieces, SAMPLE_RATE)
    speech_segments: list[tuple[float, float]] = [
        (s / SAMPLE_RATE, e / SAMPLE_RATE)
        for kind, (s, e) in zip(piece_kinds, piece_spans)
        if kind == "speech" and e > s
    ]
    manifest = {
        "speech_chunks": len(speech_chunks),
        "pause_chunks": len(parts) - len(speech_chunks),
        "total_chars": total_chars,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "model_id": model_id,
        "voice_id": voice_id,
        "sample_rate": SAMPLE_RATE,
        "duration_s": samples.shape[0] / SAMPLE_RATE,
        "short_chunk_count": len(short_chunks),
        "tone_preset": tone_preset or "",
        "time_stretch_factor": float(time_stretch_factor or 1.0),
        "chunk_lufs_target": (
            float(normalize_chunk_lufs)
            if normalize_chunk_lufs is not None else None
        ),
        "speech_segments": speech_segments,
        "warnings": (
            [f"{len(short_chunks)} chunk(s) under {CHUNK_MIN_FOR_RELIABILITY} chars — "
             "v3 may produce unstable prosody on these. Consider merging short paragraphs."]
            if short_chunks else []
        ),
    }
    return samples, SAMPLE_RATE, manifest
