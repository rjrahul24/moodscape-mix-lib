# Moodscape Mix — Project Context

Streamlit app that renders studio-grade meditation and sleep-story audio from a script + background track. ElevenLabs v3 for TTS narration (with audio tags), Pedalboard + scipy for a broadcast-quality DSP mix chain, LUFS verification gate before export.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # paste your ELEVENLABS_API_KEY
streamlit run app.py
python -m pytest tests/ -v
```

## Tech stack

Python 3.9+, Streamlit, ElevenLabs SDK (v3), Pedalboard, scipy, numpy, pyloudnorm, soundfile. ffmpeg required for M4A export.

## Architecture

### Signal flow

```
User script (plain text + [audio tags] + [pause for Xs])
  → chunker.chunk_script()  →  SpeechChunk / PauseChunk list
  → tts.synthesize_script() →  per-chunk ElevenLabs v3 API call (SHA256 cached)
       per-chunk LUFS norm → optional time-stretch → 30 ms crossfade stitch
  → mixer.render():
       Voice chain:  HPF 90 Hz (always on); all else OFF by default
                     Optional: mud cut, compressor, de-esser, presence/air EQ, reverb
       Music chain:  LPF 12 kHz → pocket EQ (-2 dB @ 2 kHz) → compressor
                     → gain → M/S widen (mid -2 dB, side ×1.15)
       Ducking:      script-aware deterministic curve (500 ms predictive descent,
                     hold during speech, S-curve release, +lift on pauses ≥1.5 s)
                     + reactive envelope follower (safety net)
                     Only 200 Hz–4 kHz band moves; bass/treble untouched
       Master bus:   HPF 30 → glue compressor → +1 dB shelf @ 12 kHz
                     → LUFS normalize to -16 → 4× oversampled TP limiter @ -1 dBTP
                     → TPDF dither (16-bit WAV)
       Verify gate:  LUFS ±0.5, TP ≤ -1.0 dBTP, LRA 3–24 LU, mono-delta ≤ 3 LU
  → WAV/MP3/M4A master + voice/music/premaster stems
```

### Module map

All source is in `meditation_mixer/`. One file = one responsibility.

| Module | Lines | Purpose | Key exports |
|---|---|---|---|
| `config.py` | 49 | Paths, env vars, constants | `SAMPLE_RATE`, `TARGET_LUFS`, `TRUE_PEAK_DB`, `LRA_RANGE`, `ELEVENLABS_API_KEY` |
| `tts.py` | 835 | ElevenLabs v3 wrapper: chunking, tone-preset reassertion, cache, crossfade stitch | `synthesize_script()`, `list_voices()`, `STABILITY_PRESETS` |
| `chunker.py` | 312 | Script parser: paragraphs → SpeechChunk/PauseChunk, markdown stripping | `chunk_script()`, `SpeechChunk`, `PauseChunk`, `neighbors()` |
| `mixer.py` | 574 | End-to-end render pipeline orchestrator | `render()`, `MixSettings`, `wav_to_m4a()` |
| `ducking.py` | 457 | Frequency-selective sidechain: reactive + script-aware dual-layer | `script_aware_duck()`, `freq_selective_duck()`, `detect_phrases_from_audio()` |
| `mastering.py` | 196 | LUFS norm, 4× TP limiter, dither, M/S width, verify gate | `normalize_lufs()`, `true_peak_limit()`, `verify_master()`, `tpdf_dither()` |
| `arrange.py` | 169 | Background looping/trimming with crossfades, silence padding | `fit_to_length()`, `apply_fades()`, `pad_voice()`, `FitReport` |
| `reverb.py` | 181 | Convolution reverb + synthetic plate IR generator | `convolution_reverb_split()`, `ensure_default_ir()`, `synthesize_plate_ir()` |
| `deess.py` | 55 | Split-band LR4 de-esser @ 6.5 kHz | `deess()` |
| `cache.py` | 55 | Content-addressed SHA256 disk cache for TTS PCM | `load()`, `store()`, `clear()` |
| `library.py` | 48 | Background file management: list, upload, load+resample | `list_backgrounds()`, `save_upload()`, `load_audio()` |
| `presets.py` | 134 | Frozen dataclass presets for content types | `PRESETS`, `MEDITATION`, `SLEEP_STORY`, `ContentPreset` |
| `logging_setup.py` | 71 | Idempotent logger: console + rotating file, RSS memory | `setup_logging()`, `rss_mb()` |

### Content types

Two presets drive all TTS and mix defaults:

| Setting | Meditation | Sleep Story |
|---|---|---|
| `pause_scale` | 2.0 (spacious) | 1.1 (minimal) |
| `tone_preset` | `[soft][slowly]` | `[calm][soft]` |
| `max_chunk_chars` | 800 (default) | 1600 (longer context) |
| `duck_range_db` | -7.0 | -4.0 (gentler) |
| `duck_release_ms` | 1200 | 1500 |
| `ramp_pause_end_scale` | 1.0 (off) | 1.6 (pauses lengthen toward end) |
| `bg_gain_db` | -13.0 | -17.0 (quieter music) |

## Key constants (load-bearing — do not change without understanding DSP implications)

All defined in `config.py`:

- `SAMPLE_RATE = 48000` — matches ElevenLabs v3 PCM output
- `TARGET_LUFS = -16.0` — Apple Podcasts standard
- `TRUE_PEAK_DB = -1.0` — safe through AAC/MP3 intersample peaks
- `LRA_RANGE = (3.0, 24.0)` — wide for spoken word with intentional dynamics
- `CHUNK_MAX_CHARS = 800` — v3 sweet spot for emotional warmth + drift resistance
- `DEFAULT_SEED = 42` — deterministic renders

## Conventions

- Type hints throughout (`from __future__ import annotations`)
- Frozen dataclasses for immutable config (`ContentPreset`, `FitReport`, `VerifyReport`)
- Content-addressed caching (SHA256 of all audio-affecting inputs)
- Docstrings explain *why*, not just *what*
- Error handling: try/except with logging, never silent failures
- Resource management: explicit `gc.collect()`, `del` large arrays, RSS monitoring
- Commit style: conventional commits (`feat:`, `docs:`, `chore:`, `fix:`)
- Voice path deliberately minimal by default — all EQ/compression/reverb is opt-in and OFF

## File layout

```
app.py                       Streamlit UI (entry point)
meditation_mixer/            Core package (14 modules)
docs/                        LLM script-writing guides + design specs
  MEDITATION_GUIDE.md        Give to LLM for meditation scripts
  SLEEP_STORY_GUIDE.md       Give to LLM for sleep story scripts
  MEDITATION_MIXING_PROMPT.md  Original design spec for the mixer
tests/                       pytest suite (4 files)
backgrounds/                 User audio files (gitignored)
outputs/                     Rendered audio + stems (gitignored)
irs/                         Impulse responses (synthetic plate auto-generated)
.cache/tts/                  TTS cache (gitignored)
logs/                        Rotating logs (gitignored)
```

## Testing

```bash
python -m pytest tests/ -v
```

| Test file | Covers |
|---|---|
| `test_presets.py` | Preset field values, registry, immutability (frozen) |
| `test_logging_setup.py` | Logger idempotency, handler counts, `rss_mb()` |
| `test_ramp.py` | `_ramp_factor` interpolation for progressive pause lengthening |
| `test_retry.py` | `_with_retries` backoff: transient vs client-error handling |

## Common tasks

- **Add a new content type**: create `ContentPreset` in `presets.py`, add to `PRESETS` dict, write guide in `docs/`
- **Add a new voice**: add `Voice()` to `MEDITATION_VOICES` list in `tts.py`
- **Change DSP parameters**: update `MixSettings` defaults in `mixer.py` (and `ContentPreset` if type-specific)
- **Trace the render pipeline**: `mixer.py` `render()` is the orchestrator — follow the numbered steps in `_render_body()`
- **Debug audio quality**: check `verify_master()` output in `mastering.py` — it flags LUFS, TP, LRA, mono-delta issues
