# Meditation Audio Mixer

Headspace-grade meditation audio from a script. **ElevenLabs v3** for narration (with audio tags like `[whispers]`, `[breathes]`, `[soft]`), **Pedalboard** + **scipy.signal** for a studio mix chain, and a strict LUFS verification gate before export.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env       # paste your ElevenLabs API key
streamlit run app.py
```

## Script format

Paragraphs separated by blank lines become TTS chunks. Lines of the form `### PAUSE Xs` (or `Xms`) become programmatic silence — they cost zero API credits and give exact pause durations.

```text
[soft] Welcome.  Find a comfortable position…
and when you're ready, [breathes] gently close your eyes.

### PAUSE 5s

[whispers] Take a slow breath in… [inhales]
…and let it go. [exhales]  [long pause]

### PAUSE 8s

[gently] Notice the weight of your body, settling.
```

Audio tags work with v3 only. The v2 fallback ignores them — use longer punctuation and `### PAUSE` instead.

## Pipeline

```
ElevenLabs v3 (PCM 48 kHz mono, chunked at ~4.4k chars with prev/next_text+seed,
               disk-cached by content hash, tone preset `[soft][slowly]`
               reasserted at every chunk that lacks a leading [tag])
        ↓
Per chunk: pyloudnorm to -19 LUFS  → Rubber Band R3 time-stretch ×1.18
           (preserve_formants=True, smooth transients, long FFT window)
        ↓
Equal-power crossfade stitch (30 ms) + programmatic ### PAUSE silences
        ↓
Voice: HPF 90 → mud cut → Compressor → split-band De-esser →
       Presence (+2 dB @ 4 kHz) → Air (+1.5 dB shelf @ 10 kHz) →
       Convolution reverb send (plate IR, 25 ms pre-delay, HPF 250 Hz,
       wet ducked during voice / lifted +4 dB during long pauses)
        ↓
Background loop+crossfade → fades → LPF 12 kHz → static pocket EQ
                                    (-2 dB peak @ 2 kHz, Q 0.7) →
                                    Compressor → Gain →
                                    M/S widen (mid -2 dB, side ×1.15)
        ↓
Script-aware sidechain ducking: deterministic curve from phrase
timestamps — 300 ms predictive descent, -9 dB hold, 700 ms S-curve
release, +1.5 dB lift during pauses ≥ 1.5 s. Combined with reactive
detector (preserves +lift; reactive deepens negative ducks). Only the
200 Hz – 4 kHz band of music moves.
        ↓
Master: HPF 30 → glue Compressor → +1 dB shelf @ 12 kHz →
        LUFS normalize to -16 → 4× oversampled true-peak Limiter
        at -1 dBTP → TPDF dither for 16-bit WAV
        ↓
Verification gate: LUFS ±0.5 / TP ≤ -1.0 dBTP / LRA 5-18 LU /
                   |mono-sum delta| ≤ 3 LU
        ↓
WAV/MP3 master + voice/music/premaster stems in outputs/
```

## Where to find royalty-free background sounds

- [Pixabay Music](https://pixabay.com/music/) — CC0
- [Free Music Archive](https://freemusicarchive.org/) — filter by CC license
- [Freesound](https://freesound.org/) — filter by **CC0** / Public Domain
- [Uppbeat](https://uppbeat.io/) — free tier with attribution

For premium reverb IRs (drop into `irs/`): the [OpenAIR library](https://www.openair.hosted.york.ac.uk/) at York, or Samplicity's free Bricasti M7 IR pack. A synthetic plate IR is generated on first run so the app works out of the box.

## Layout

```
app.py                       Streamlit UI
meditation_mixer/
  config.py                  Paths, env, targets (48k, -16 LUFS, -1 dBTP)
  tts.py                     v3 wrapper with chunking, prev/next/seed, cache
  chunker.py                 Script → speech + pause chunks
  cache.py                   Content-addressed disk cache for TTS PCM
  library.py                 Background file management
  arrange.py                 Loop+crossfade, fades, padding
  ducking.py                 Frequency-selective sidechain with look-ahead
  reverb.py                  Convolution reverb + synthetic plate generator
  deess.py                   Split-band Linkwitz-Riley de-esser
  mastering.py               4× true-peak limiter, dither, M/S width, verify
  mixer.py                   End-to-end pipeline + stem export
backgrounds/                 Your royalty-free sources (gitignored)
irs/                         Impulse responses (synthetic plate auto-generated)
outputs/                     Master + stems (gitignored)
.cache/tts/                  Cached ElevenLabs PCM (gitignored)
```

## Target spec

| Metric | Target | Why |
|---|---|---|
| Sample rate (internal) | 48 kHz float32 | Headroom for reverb/EQ, matches v3 output |
| Integrated LUFS | −16.0 ± 0.5 | Apple Podcasts target; correct on earbuds and headphones |
| True peak | ≤ −1.0 dBTP | Safe through AAC/MP3 intersample peaks |
| LRA | 6–9 LU (4–10 acceptable) | Keeps breath dynamics audible, not crushed |
| Delivery | 16-bit WAV (dithered) or MP3 | WAV for archive, MP3 for sharing |
| Stems | voice / music / premaster | Re-mix or re-master without re-paying for TTS |
```
