import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
BACKGROUNDS_DIR = ROOT / "backgrounds"
OUTPUTS_DIR = ROOT / "outputs"
CACHE_DIR = ROOT / ".cache" / "tts"
IR_DIR = ROOT / "irs"

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# Internal sample rate. 48 kHz aligns with ElevenLabs `pcm_48000`,
# gives more headroom for reverb/EQ, and pairs cleanly with video.
SAMPLE_RATE = 48000

# Master targets (BS.1770-4 / DeMan filter).
TARGET_LUFS = -16.0
TRUE_PEAK_DB = -1.0
# LRA: 4-10 LU is the standard *music* range. Meditation tracks are spoken
# word with intentionally wide dynamics — whispered passages, breath holds,
# and louder anchor lines — so they naturally land higher. EBU / industry
# guidance for spoken/long-form content is roughly 5-18 LU; we use that as
# the accept window. Anything outside still flags as a render bug.
LRA_RANGE = (5.0, 18.0)

# v3 is ElevenLabs' recommended long-form model and supports audio tags
# ([whispers], [breathes], [soft] etc.) which v2 ignores.
DEFAULT_MODEL_ID = "eleven_v3"
FALLBACK_MODEL_ID = "eleven_multilingual_v2"

# Stable seed so identical inputs give identical outputs across runs.
DEFAULT_SEED = 42

SUPPORTED_BG_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif"}

# Script chunking. Every chunk boundary is a place where v3 prosody and
# timbre can drift, so we keep chunks as LARGE as the API allows. v3's
# hard per-request limit is 5000 chars; we cap merging at 4400 to stay
# safely under that. Most meditation paragraphs between `### PAUSE`
# markers will now collapse into a single TTS call, eliminating in-section
# drift entirely. (Drift across `### PAUSE` boundaries is handled
# separately via request_id stitching in tts.py.) Below ~250 chars v3
# starts to wobble, so we still warn under that threshold.
CHUNK_MAX_CHARS = 4400
CHUNK_MIN_CHARS = 250
