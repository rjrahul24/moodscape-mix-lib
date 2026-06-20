# Prompt: Add instrumental-upload + professional meditation mixing

## Context & goal

This project generates **guided meditations**. TTS narration is already produced by a separate pipeline (not ElevenLabs). I want to add the ability to **upload an instrumental/background audio file** and **mix it with the TTS** using a broadcast-grade meditation mixing pipeline — the same accuracy, cleanliness, ducking, and loudness mastering used in a reference project of mine.

The reference pipeline is a Python package (`pedalboard` + `scipy` + `numpy` + `pyloudnorm` + `soundfile`). I want you to **port that mixing/mastering engine into this project** as a self-contained module, then wire it to a "upload background + mix" flow. **Do not** port any ElevenLabs/TTS generation code — only the post-TTS mixing, ducking, and mastering. The voice arrives as a mono float32 array (or a file we decode to one); everything downstream is provider-agnostic.

## What to build

A module (suggest `audio_mix/` or matching this repo's conventions) that exposes a single entry point:

```python
render(voice: np.ndarray, sr: int, bg_path: Path, settings: MixSettings,
       output_path: Path, output_format="wav",
       speech_segments: list[tuple[float,float]] | None = None) -> dict
```

`voice` is 1-D mono float32 in [-1, 1]. `bg_path` is the uploaded instrumental. Returns a manifest dict with the measured LUFS / true-peak / LRA / mono-sum-delta and how the background was fitted. **`speech_segments` must be optional** — when our TTS layer can give phrase timestamps, pass them; otherwise the ducker auto-detects phrases from the voice envelope (see below). This is the key decoupling point that makes it work without ElevenLabs.

## Signal flow (replicate exactly — these values are tuned, not arbitrary)

Internal sample rate **48 kHz**; everything resamples to it on load; output is stereo.

**1. Arrange.** Pad voice with `pre_roll_s=3.0` / `post_roll_s=5.0` silence → defines the target length. Load + resample the uploaded background, force to stereo, then **fit to the exact target length**:
- bg longer than target → trim tail (master fade-out hides the cut)
- bg shorter → seamless loop with **500 ms equal-power crossfades** at each seam (crossfade auto-shrinks to ≤25% of source; falls back to hard tiling if source < ~4 ms)
- bg equal → used as-is
- Then apply linear `bg_fade_in_s=4.0` / `bg_fade_out_s=6.0`.

**2. Voice chain (deliberately minimal — keep TTS un-coloured).** Only an always-on **90 Hz high-pass** (sub-rumble). Everything else is **opt-in and OFF by default**: mud cut (300 Hz peak), compressor (−22 dB / 2.5:1 / 12 ms / 120 ms), presence (4 kHz peak), air (10 kHz high-shelf), split-band de-esser (LR4 crossover @ 6.5 kHz, compress only the high band), and convolution reverb. Reverb especially must default off — plate reverb on close-mic'd TTS is the main source of "echoey/robotic" character.

**3. Music chain.** High-shelf **+3 dB @ 4500 Hz** (Fletcher-Munson compensation so the bed stays bright when ducked) → **LPF 12 kHz** safety ceiling → static **−2 dB peak dip @ 2000 Hz, Q 0.7** ("speech pocket" so the dynamic ducker can move less) → Compressor (−20 dB / 2:1 / 20 ms / 400 ms) → Gain (`bg_gain_db=-13.0`) → **M/S widen** (`width=1.15`, `mid_gain_db=-2.0` to tuck the centre for the centered voice).

**4. Ducking (the core of the "breathing" feel).** Frequency-selective sidechain that ducks **only the 200 Hz–4 kHz mid band** of the music (bass drones + high shimmer stay full). Two layers combined:

- **Envelope-based VAD phrase detection (PRIMARY — since this project has no TTS timestamps):** Voice-activity detection via RMS-envelope thresholding at −40 dB, with inter-word gaps < 250 ms merged and phrases < 150 ms dropped as noise. This generates the `speech_segments` list that feeds into the script-aware curve below.

- **Script-aware deterministic curve:** From phrase `(start,end)` timestamps (whether from TTS metadata or VAD-detected), build a gain-in-dB envelope — predictive cubic-S-curve descent starting `pre_descent_ms=500` *before* each phrase onset, held duck at `duck_range_db=-7.0` during speech, S-curve release over `release_ms=1200`, and a **+2 dB lift during pauses ≥ 1.5 s** so the bed breathes. Zero-phase Butterworth smoothed (~5–8 Hz) to round keyframe corners.

- **Reactive envelope follower** (safety net): band-limited RMS detector @ 200 Hz–4 kHz, threshold `-30 dB`, asymmetric attack `15 ms` / release `1200 ms`, `10 ms` look-ahead.

- **Combine** them with the rule: where the script asks for positive lift, script wins (a naive `np.minimum` would let the reactive release tail erase the lift); elsewhere take the more-restrictive of the two so off-script breaths still duck. When `speech_segments` is explicitly provided (future enhancement), use those; otherwise use VAD-detected phrases.

**5. Master bus.** Sum voice (at `voice_gain_db=-3.0`) + ducked music → HPF 30 → glue compressor (−12 dB / 1.5:1 / 50 ms / 200 ms) → +1 dB high-shelf @ 12 kHz → **LUFS normalize to -16 FIRST, then 4×-oversampled true-peak limit to -1 dBTP** (order is critical — normalizing after limiting would re-exceed the ceiling). The limiter uses a look-ahead minimum-filter brickwall with a `safety_margin_db=0.3` internal headroom so measured TP lands under spec. Optional TPDF dither for 16-bit WAV.

**6. Verify gate.** Measure integrated LUFS (BS.1770-4 / DeMan filter), true-peak, LRA, and mono-sum-delta; flag issues if LUFS off by > 1 LU, TP > -1, LRA outside **(3.0, 24.0)** LU [wide because spoken meditation has intentionally wide dynamics], or mono-sum-delta > 3 LU. Return these in the manifest; don't hard-fail.

**7. Stems.** Optionally write `voice.wav` / `music.wav` / `premaster.wav` next to the master so re-mixing is free.

## Implementation notes

There is no reference source to copy — implement the DSP from this spec. **Treat every numeric constant above as exact and load-bearing** (they're tuned, not arbitrary): sample rate 48 kHz, voice HPF 90 Hz, music shelf +3 dB @ 4500 Hz, LPF 12 kHz, pocket −2 dB @ 2000 Hz Q 0.7, music comp −20/2:1/20 ms/400 ms, `bg_gain_db=-13`, M/S width 1.15 + mid −2 dB, duck band 200 Hz–4 kHz, duck depth −7 dB, pre-descent 500 ms, release 1200 ms, pause-lift +2 dB @ ≥1.5 s, reactive threshold −30 dB / attack 15 ms / look-ahead 10 ms, `voice_gain_db=-3`, master HPF 30 + glue comp −12/1.5:1/50 ms/200 ms + 12 kHz shelf +1 dB, **normalize to −16 LUFS then 4× true-peak limit to −1 dBTP (in that order)**, limiter safety margin 0.3 dB, LRA accept window 3–24 LU. Use `pyloudnorm` with `filter_class="DeMan"` for all loudness measurement. Use `scipy.signal.butter`/`sosfilt` for filters and `resample_poly` for oversampling/resampling.

## Reference: Existing architecture from moodscape-mix-lib

The reference implementation demonstrates:
- **Module separation**: `config.py` (constants), `mixer.py` (render entry point), `ducking.py` (frequency-selective + script-aware ducking), `mastering.py` (LUFS / true-peak / dither / verification), `arrange.py` (looping + fitting + fades), `library.py` (file I/O + upload handling), `reverb.py` (convolution reverb), `deess.py` (split-band de-esser).
- **Minimal voice path by default**: the voice chain is deliberately kept un-coloured; all EQ/compression/reverb is opt-in and defaults off.
- **Exact constant tuning**: every dB value, frequency, ms timing, and LU boundary is deliberate and tested across real meditation content.

## Deliverables

1. Ported, self-contained mixing module with the `render()` entry point and a `MixSettings` dataclass exposing all the tuned defaults above.
2. A background-upload flow (validate ext against `{.wav,.mp3,.flac,.ogg,.m4a,.aiff,.aif}`, resample on load, sanitize filenames, overwrite-by-name).
3. A voice adapter that takes our TTS output and yields `(voice_array, sr)`.
4. Wiring so a user uploads an instrumental + supplies narration and gets a mastered stereo meditation back, plus the verification manifest surfaced in the UI/response.
5. Tests: round-trip a synthetic voice + a short instrumental through `render()` and assert the master lands at -16±1 LUFS, ≤ -1 dBTP, and bg fitting handles longer/shorter/equal sources.

## Constraints
- Dependencies: `pedalboard>=0.9`, `numpy>=1.26`, `scipy>=1.13`, `soundfile>=0.12`, `pyloudnorm>=0.1.1`. No ElevenLabs/TTS deps.
- Before designing, **read this project's existing structure and conventions** (framework, storage, how audio/files are currently handled) and match them.
- Keep the voice path un-coloured by default; all coloration opt-in.
- Since this project's TTS does not expose phrase timestamps, **the VAD-based phrase detection is the primary path** — the script-aware ducking curve is driven by envelope detection, not script metadata.

---

**Before writing code, propose a short integration plan** (module placement, voice-adapter shape, upload storage, UI/API touch-points) and confirm it fits this repo, then implement.
