"""Parse a meditation script into a sequence of TTS chunks and programmatic pauses.

Script format (matches `docs/MEDITATION_GUIDE.md`):

    [soft] Welcome.  Find a comfortable position…

    ### PAUSE 5s

    [whispers] Take a slow breath in… [inhales]

- Paragraphs are separated by blank lines and become TTS chunks.
- A line of the form `### PAUSE Xs` (or `Xms`) becomes programmatic silence —
  not a TTS call. ElevenLabs' `<break>` tag caps at 3 s and excessive use
  causes prosody artifacts, so we never use it; long pauses are pure silence.

Chunks are merged greedily up to `CHUNK_MAX_CHARS` (default 1200) so v3 gets
enough context to stabilize prosody. If a single paragraph exceeds the per-
request safety ceiling (`HARD_MAX_CHARS`, 4500 < the 5000 v3 limit), we split
it on sentence boundaries — never inside an `[audio tag]`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .config import CHUNK_MAX_CHARS

# ElevenLabs v3 has a 5000-char per-request hard limit. We stay under it.
HARD_MAX_CHARS = 4500

_PAUSE_RE = re.compile(
    r"^\s*###\s*PAUSE\s+(?P<n>\d+(?:\.\d+)?)\s*(?P<u>ms|s|sec|seconds?)?\s*$",
    re.IGNORECASE,
)

# Alternative pause syntax from the one-sentence-per-line format:
#   [pause for 5 seconds]  /  (pause for 3 s)  /  {silence 10 seconds}
# This makes the chunker accept scripts written in the style of script.txt
# alongside the canonical ### PAUSE Xs format.
_INLINE_PAUSE_RE = re.compile(
    r"^\s*(?:\(|\[|\{)\s*(?:pause|silence)\s*(?:for)?\s*"
    r"(?P<n>\d+(?:\.\d+)?)\s*(?P<u>seconds?|secs?|s)\s*(?:\)|\]|\})\s*$",
    re.IGNORECASE,
)

# --- Markdown stripping (safety net) -------------------------------- #
# TTS models interpret markdown symbols as literal text or timing cues,
# resulting in robotic beats and vocalised bullet characters. The
# docs/MEDITATION_GUIDE already tells users to write plain text, but this
# catches any formatting that slips through.  `### PAUSE` lines are
# explicitly preserved since that is our own pause-marker syntax.

_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")        # **bold**
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")  # *italic*
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)  # # Heading
_MD_BULLET_RE = re.compile(r"^[ \t]*[-*+]\s+", re.MULTILINE)  # - bullet
_MD_NUMLIST_RE = re.compile(r"^[ \t]*\d+\.\s+", re.MULTILINE)  # 1. item

# Multiline variant of _PAUSE_RE — needed because _strip_markdown operates
# on the full script text, not individual lines.
_PAUSE_ML_RE = re.compile(
    r"^\s*###\s*PAUSE\s+\d+(?:\.\d+)?\s*(?:ms|s|sec|seconds?)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_markdown(text: str) -> str:
    """Remove common markdown formatting while preserving ``### PAUSE`` lines.

    This is a best-effort safety net — it handles the most common formatting
    artifacts (**bold**, *italic*, headings, bullets, numbered lists) without
    touching audio-tag brackets ``[soft]`` or our pause-marker syntax.
    """
    # Protect ### PAUSE lines from the heading stripper by temporarily
    # swapping them with indexed sentinels that no regex can match.
    pause_lines: list[str] = []

    def _save_pause(m: re.Match) -> str:
        idx = len(pause_lines)
        pause_lines.append(m.group(0))
        return f"\x00PAUSE{idx}\x00"

    protected = _PAUSE_ML_RE.sub(_save_pause, text)

    # Strip markdown constructs.
    protected = _MD_BOLD_RE.sub(r"\1", protected)    # **bold** → bold
    protected = _MD_ITALIC_RE.sub(r"\1", protected)  # *italic* → italic
    protected = _MD_HEADING_RE.sub("", protected)     # # Heading → Heading
    protected = _MD_BULLET_RE.sub("", protected)      # - item → item
    protected = _MD_NUMLIST_RE.sub("", protected)     # 1. item → item

    # Restore ### PAUSE lines.
    for idx, original in enumerate(pause_lines):
        protected = protected.replace(f"\x00PAUSE{idx}\x00", original)
    return protected


@dataclass
class SpeechChunk:
    text: str


@dataclass
class PauseChunk:
    seconds: float


Chunk = SpeechChunk | PauseChunk


def _parse_pause(line: str) -> float | None:
    m = _PAUSE_RE.match(line)
    if not m:
        m = _INLINE_PAUSE_RE.match(line)
    if not m:
        return None
    n = float(m.group("n"))
    unit = (m.group("u") or "s").lower()
    return n / 1000.0 if unit == "ms" else n


def _split_paragraphs(script: str) -> list[str | float]:
    """Yield paragraphs as strings and pause markers as floats (seconds)."""
    items: list[str | float] = []
    buf: list[str] = []

    def flush():
        if buf:
            para = "\n".join(buf).strip()
            if para:
                items.append(para)
            buf.clear()

    for raw in script.splitlines():
        pause = _parse_pause(raw)
        if pause is not None:
            flush()
            items.append(pause)
            continue
        if not raw.strip():
            flush()
            continue
        buf.append(raw)
    flush()
    return items


# Split on sentence terminators that are followed by whitespace + capital /
# audio tag / quote / opening paren. Treat ellipses (… or ...) as soft pauses
# and try not to split there. Never split inside an `[audio tag]`.
_SENTENCE_END = re.compile(
    r"(?<=[.!?])(?<!\.\.\.)\s+(?=[\[\"\'A-Z(])"
)


def _split_outside_brackets(text: str, splitter: re.Pattern[str]) -> list[str]:
    """Apply `splitter` only at positions NOT enclosed in [audio tags]."""
    parts: list[str] = []
    depth = 0
    last = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "[":
            depth += 1
        elif ch == "]" and depth > 0:
            depth -= 1
        if depth == 0:
            m = splitter.match(text, i)
            if m and m.end() > m.start():
                parts.append(text[last:i].rstrip())
                last = m.end()
                i = m.end()
                continue
        i += 1
    tail = text[last:].strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def _split_long_paragraph(para: str, max_chars: int) -> list[str]:
    """Break a paragraph that is too long for one TTS request into pieces
    along sentence boundaries. Falls back to whitespace splits if a single
    sentence is still too long (rare, but possible with run-on writing).
    """
    if len(para) <= max_chars:
        return [para]
    sentences = _split_outside_brackets(para, _SENTENCE_END)
    if not sentences:
        sentences = [para]

    chunks: list[str] = []
    cur = ""
    for s in sentences:
        if len(s) > max_chars:
            # Sentence itself too long; hard-split on word boundaries.
            if cur:
                chunks.append(cur)
                cur = ""
            words = s.split(" ")
            buf = ""
            for w in words:
                if not buf:
                    buf = w
                elif len(buf) + 1 + len(w) <= max_chars:
                    buf = f"{buf} {w}"
                else:
                    chunks.append(buf)
                    buf = w
            if buf:
                cur = buf
            continue
        if not cur:
            cur = s
        elif len(cur) + 1 + len(s) <= max_chars:
            cur = f"{cur} {s}"
        else:
            chunks.append(cur)
            cur = s
    if cur:
        chunks.append(cur)
    return chunks


def chunk_script(
    script: str,
    max_chars: int = CHUNK_MAX_CHARS,
    hard_max_chars: int = HARD_MAX_CHARS,
    pause_scale: float = 1.0,
) -> list[Chunk]:
    """Parse a script into an ordered list of speech and pause chunks.

    Adjacent paragraphs are merged into the same speech chunk until adding
    the next paragraph would exceed `max_chars`. A pause marker (either
    ``### PAUSE Xs`` or ``[pause for Xs]``) breaks the current speech
    chunk. Any single paragraph longer than `hard_max_chars` is sentence-
    split so no TTS request ever exceeds v3's 5 000-char limit.

    This design follows the pattern used by the reference
    ``eleven_meditation_tts.py``: all text between pause markers is kept
    together as one TTS call. This gives v3 enough context to maintain
    stable voice timbre (preventing drift) while pauses provide natural
    breathing room between sections.

    `pause_scale` multiplies every pause duration uniformly — a single
    knob for "stretch all breathing room" without rewriting the script.
    Use values >1 for slower/more spacious meditations, <1 for tighter
    ones. 1.0 keeps the script's literal pause lengths.
    """
    # Safety net: strip common markdown formatting (bold, italic, headings,
    # bullets, numbered lists) that users may paste in.  `### PAUSE` lines
    # are preserved.  (Ref: Optimizations12.md §1.1 — eradicate markdown
    # from the generation payload.)
    script = _strip_markdown(script)
    items = _split_paragraphs(script)
    scale = max(0.0, float(pause_scale))
    # First, expand any oversize paragraphs into smaller paragraphs. Apply
    # `pause_scale` to pause markers in this same pass so chunking sees the
    # final pause durations.
    expanded: list[str | float] = []
    for it in items:
        if isinstance(it, float):
            expanded.append(it * scale)
        elif len(it) > hard_max_chars:
            expanded.extend(_split_long_paragraph(it, hard_max_chars))
        else:
            expanded.append(it)

    out: list[Chunk] = []
    current = ""

    def flush_speech():
        nonlocal current
        if current.strip():
            out.append(SpeechChunk(text=current.strip()))
        current = ""

    for item in expanded:
        if isinstance(item, float):
            flush_speech()
            if item > 0:
                out.append(PauseChunk(seconds=item))
            continue
        para: str = item
        if not current:
            current = para
        elif (
            len(current) + len(para) + 2 <= max_chars
            and len(current) + len(para) + 2 <= hard_max_chars
        ):
            current = f"{current}\n\n{para}"
        else:
            flush_speech()
            current = para

    flush_speech()
    return out


def neighbors(chunks: list[Chunk]) -> list[tuple[str | None, str | None]]:
    """For each speech chunk, return (previous_text, next_text) drawn from the
    nearest neighbouring speech chunks (skipping pauses). v3 has no request
    stitching, so this is the approved prosody-continuity path.
    """
    speech_idxs = [i for i, c in enumerate(chunks) if isinstance(c, SpeechChunk)]
    result: list[tuple[str | None, str | None]] = []
    for pos, idx in enumerate(speech_idxs):
        prev = chunks[speech_idxs[pos - 1]].text if pos > 0 else None
        nxt = chunks[speech_idxs[pos + 1]].text if pos + 1 < len(speech_idxs) else None
        result.append((prev, nxt))
    return result
