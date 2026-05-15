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
# With the default clean-voice path (no compression, no reverb), the
# voice dynamics are passed through untouched, so meditation masters
# commonly land in the 12-22 LU band. We accept 3-24 LU; anything
# outside that still flags as a render bug.
LRA_RANGE = (3.0, 24.0)

# v3 is ElevenLabs' recommended long-form model and supports audio tags
# ([whispers], [breathes], [soft] etc.) which v2 ignores.
DEFAULT_MODEL_ID = "eleven_v3"
FALLBACK_MODEL_ID = "eleven_multilingual_v2"

# Stable seed so identical inputs give identical outputs across runs.
DEFAULT_SEED = 42

SUPPORTED_BG_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif"}

# Script chunking. v3 performs best with chunks under 800 characters to
# maintain emotional warmth and prevent vocal drift on long passages.
# Below ~250 chars v3 starts to wobble, so we still warn under that threshold.
CHUNK_MAX_CHARS = 800

# Legacy fallback for extended chunking up to 4400 chars.
CHUNK_MAX_CHARS_EXTENDED = 4400
