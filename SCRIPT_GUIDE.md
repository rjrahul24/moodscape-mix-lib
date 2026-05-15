# Meditation Script Guide — for use with the Meditation Audio Mixer

---

## Part 1 — Hard rules the LLM must follow

These are non-negotiable. The Mixer's parser depends on them.

1. **Output is plain text only.** No markdown headings, no bullets, no preamble like *"Here is your script…"*, no closing remarks. Just the meditation, ready to paste.
2. **One paragraph per beat.** Each paragraph is a single TTS chunk. Separate paragraphs with **one blank line**. Do not indent.
3. **Long pauses use the exact syntax `### PAUSE Xs`** on a line by itself, surrounded by blank lines. `Xs` is seconds (e.g. `### PAUSE 8s`); `Xms` is milliseconds. These are *programmatic silence* — they cost nothing and are exact to the millisecond. Use them for any pause **longer than ~2 seconds**.
4. **Short pauses (≤ 2 s) use punctuation, not tags.** Specifically:
   - `…` (ellipsis) — soft hesitation, breath-length pause, ~0.5–1 s
   - `—` (em-dash, surrounded by spaces) — stronger break, ~1–1.5 s
   - `.` (period) — sentence boundary, natural pause
   - `,` (comma) — slight in-line pause
5. **Audio tags use square brackets**, lower-case, at the position where the effect should start. Examples: `[soft]`, `[whispers]`, `[exhales]`. Tags **never** appear inside another tag.
6. **Every paragraph starts with a tone tag.** The first token of each paragraph is a tone-setting tag like `[soft]`, `[calm]`, `[serene]`, `[warmly]`, or `[whispers]`. Tone tags fade across paragraphs in v3, so they **must be re-asserted at the start of each one**.
7. **Per-paragraph length: 250–800 characters.** Below 250 chars v3 produces unstable prosody; chunks above 800 chars are prone to vocal drift. Aim for 4–8 sentences per paragraph.
8. **No `<break>` tags, no SSML, no `[long pause]` repeated 5 times.** Pauses go through `### PAUSE Xs` only. ElevenLabs explicitly warns that `<break>` and repeated pause tags cause speed-ups and audio artifacts.
9. **No stage directions outside tags.** Don't write *"(softly)"* or *"--in a quiet voice--"*. The model only obeys things inside `[…]` and `### PAUSE`.
10. **Total length budget:** 5-min meditation ≈ 600 spoken words ≈ 3,500 characters of speech. 10-min ≈ 1,200 words ≈ 7,000 chars. 20-min ≈ 2,200 words ≈ 13,000 chars. Add `### PAUSE` time on top.

---

## Part 2 — Audio tag reference (verified for Eleven v3)

Place the tag **just before** the speech you want it to affect. Tags are case-insensitive but lower-case keeps the script readable. Tags after the first word of a paragraph are *transient* and only affect that line — they don't reset the paragraph's overall tone.

### Tone / delivery (use one at the start of every paragraph)

| Tag | Effect | Best for |
|---|---|---|
| `[soft]` | Warm, low-volume delivery. The workhorse tone for guided meditation. | Default tone tag |
| `[whispers]` | Hushed, intimate, almost breathy. | Sleep meditations, vulnerable moments |
| `[calm]` | Even, measured, grounded. | Body-scan, focus meditations |
| `[serene]` | Spacious, unhurried, slightly bright. | Open-awareness, nature visualizations |
| `[gently]` | Tender, careful. | Instructions, transitions |
| `[warmly]` | Friendly, embracing. | Welcomes, affirmations, lovingkindness |
| `[reassuringly]` | Steady, parental. | Anxiety meditations, "it's okay…" lines |
| `[slowly]` | Reduces pace within the line. | Counting breaths, closing lines |
| `[reflective]` | Inward, thoughtful. | Reframing, self-inquiry prompts |
| `[inner monologue]` | Quieter, more private register. | Visualization, dream-like passages |

### Breath / body (use mid-line, near the verb)

| Tag | What it produces |
|---|---|
| `[exhales]` | Audible out-breath. Single use per sentence. |
| `[inhales]` | Audible in-breath. |
| `[breathes]` | A complete breath cycle. |
| `[sighs]` | A relaxed, slow sigh. Excellent at the top of a paragraph after `### PAUSE`. |
| `[breathing heavily]` | Use sparingly — only for grounding/embodied moments. |
| `[yawns]` | A real yawn. Strong for sleep meditations near the end. |
| `[swallows]` | Subtle. Useful for naturalness, but use rarely. |

### Pause / pacing (only inside a paragraph; for >2 s use `### PAUSE`)

| Tag | What it produces |
|---|---|
| `[pauses]` | A brief in-line pause, similar to a comma but stronger. |
| `[dramatic pause]` | A noticeably longer in-line pause. Use sparingly. |

### Tags to AVOID for meditation

- `[laughs]`, `[giggles]`, `[snorts]`, `[crying]`, `[shouts]`, `[angry]`, `[sarcastic]` — wrong register.
- `[applause]`, `[gunshot]`, `[door creaks]`, `[explosion]` — wrong genre.
- Any "strong X accent" tag — drift in voice across chunks.

### How tags compose

You can stack two tags at the start of a paragraph for compound delivery: `[soft] [slowly]` or `[whispers] [reflective]`. Don't stack more than two.

You can place a transient tag mid-paragraph for a single beat: *"`[soft]` Notice the weight of your body, `[exhales]` settling."*

---

## Part 3 — Punctuation, pacing, and emphasis

Eleven v3 listens to punctuation more carefully than v2.

| Mark | Effect |
|---|---|
| `,` (comma) | Light in-line pause (~150 ms). Use generously for rhythm. |
| `.` (period) | Full sentence boundary, natural prosody drop. |
| `…` (ellipsis, single character) | Soft hesitation, ~0.5–1 s. The single most useful punctuation mark for meditation. Use *between thoughts within a sentence*. Don't overuse — three or four per paragraph max. |
| ` — ` (em-dash with spaces) | Stronger break than ellipsis. Use for definitive pause inside a sentence. |
| Paragraph break | Full pause and prosody reset. |
| **CAPITALIZATION** | Emphasis. **Use for at most one or two words per paragraph.** For meditation this is rare — usually you don't need it. |
| Repeated periods like `...` | Treated like an ellipsis. Prefer the single character `…`. |

**Two spaces after a sentence** (e.g. *"Welcome.  Find a comfortable position."*) is a hint to the model to take a slightly longer breath at the sentence break. Optional but helpful.

---

## Part 3b — Pacing for slow, relaxing delivery

Professional meditation apps (Headspace, Calm) deliver at **80–100 effective WPM** — far slower than normal speech (~150 WPM). The Mixer achieves this through **three automatic layers** plus your script-writing choices:

### What the system does automatically (you don't need to)

1. **API speed = 0.80** — the slowest clean setting before v3 starts warping vowels.
2. **`[slowly]` tag injected on every chunk** — even if your paragraph starts with `[calm]` or `[whispers]`, the system auto-appends `[slowly]` for pacing. You do NOT need to write `[slowly]` yourself.
3. **Inter-sentence pause injection** — the system automatically inserts a soft ellipsis pause (`…`) between sentences that don't already have one. This adds ~0.5–1 s of breathing room at every sentence boundary, mimicking the way professional narrators breathe between thoughts.

### What YOU control through the script

The biggest lever for pacing is **how you write**, not how fast the voice speaks.

**Keep sentences short.** 8–15 words per sentence. Each sentence = one thought. Long, complex sentences feel rushed even at a slow speed.

```
❌  Notice the weight of your body pressing down into the chair and feel the support beneath you.
✅  Notice the weight of your body.  Feel the support beneath you.
```

**Use `### PAUSE` generously.** The system doubles all pause durations by default (`pause_scale=2.0`), so `### PAUSE 4s` becomes 8 seconds of silence. Use pauses between every breathing cue and between major sections.

**Use ellipses (`…`) for mid-sentence breath pauses.** The system handles inter-sentence pauses automatically, but YOU control mid-sentence rhythm:

```
Take a slow breath in… filling the chest… then the belly.
```

**Use em-dashes (` — `) for stronger breaks.** Em-dashes produce a definitive ~1–1.5 s pause:

```
The jaw — let it unclench.  The shoulders — dropping away from the ears.
```

**Space your breathing cues.** Don't stack `[inhales]` and `[exhales]` in the same sentence. Give each its own beat:

```
❌  Breathe in [inhales] and out [exhales] slowly.
✅  Breathe in… [inhales]

### PAUSE 4s

And let it go.  [exhales]
```

### Effective WPM guide

| Target feel | Spoken WPM | How to achieve |
|---|---|---|
| Conversational (too fast) | 120–150 | Long sentences, few pauses |
| Calm narration | 100–120 | Short sentences, some pauses |
| **Guided meditation** | **80–100** | Short sentences, generous `### PAUSE`, ellipses |
| Deep relaxation / sleep | 60–80 | Very sparse text, long `### PAUSE 10-20s`, `[whispers]` |

---

## Part 4 — Structural template for a guided meditation

Use this skeleton. Numbers in parentheses are typical durations for a 10-minute meditation; scale linearly for other lengths.

```
[warmly] WELCOME (15-30 s spoken)
- Greet the listener. Invite them to get comfortable.
- 1-2 sentences. Tone tag: [warmly] or [soft].

### PAUSE 3s

[gently] SETTLE-IN (60-90 s spoken)
- Invite them to close their eyes, notice their body, drop the day.
- Use [exhales] once, near the end of the paragraph.

### PAUSE 5s

[calm] BREATH ANCHOR (90-120 s spoken)
- Direct attention to the breath. Cue 3-5 conscious breaths.
- Place `[inhales]` and `[exhales]` exactly where you want the listener's breath cycle.
- Insert `### PAUSE 4s` between cued breaths if pacing the breath count.

### PAUSE 8s

[soft] CORE PRACTICE (4-6 minutes spoken)
- The meat of the meditation: body scan, visualization, lovingkindness phrases, etc.
- 3-5 paragraphs, each starting with a tone tag.
- `### PAUSE 8-15s` between paragraphs for absorption.
- Re-cue the breath every 60-90 seconds with [exhales].

[reflective] BRIEF REFRAME (30-60 s spoken)
- One short paragraph offering a frame or affirmation.

### PAUSE 10s

[soft] [slowly] CLOSING (45-60 s spoken)
- Slowly bring attention back. Notice the body, the sounds.
- Final invitation: "When you're ready, gently open your eyes."
- Use [slowly] tone. End with a single sentence.

### PAUSE 3s
```

**For sleep meditations**, replace the closing with a "drift off" arc: longer pauses (10–20 s), `[whispers]` tone, more `[yawns]` and `[exhales]`, no "open your eyes" instruction.

---

## Part 5 — Full annotated example

This is exactly the format the Mixer expects. Notice: every paragraph starts with a tone tag, pauses use `### PAUSE Xs`, ellipses and em-dashes for in-line beats.

```
[warmly] Welcome.  Find a comfortable position — somewhere you can settle in, fully supported.  Let the chair, the cushion, or the floor hold your weight.

### PAUSE 3s

[gently] When you're ready… softly close your eyes.  Or simply let your gaze rest on a point in front of you, unfocused.  [exhales] And let yourself arrive here, just as you are.

### PAUSE 5s

[calm] Take a slow breath in through the nose… [inhales] …filling the chest, then the belly.  And then a long, easy exhale out through the mouth.  [exhales]

### PAUSE 4s

[calm] Again.  In through the nose… [inhales] …pause at the top… and out, releasing whatever you're holding.  [exhales]

### PAUSE 6s

[soft] Now let the breath find its own rhythm.  You don't need to control it.  Just notice — the rise, the fall, the small pause between.

### PAUSE 10s

[soft] Begin to scan your body, top down.  Notice the crown of your head.  The forehead, soft.  The jaw — let it unclench.  The shoulders, dropping away from the ears.  [exhales]

### PAUSE 8s

[gently] Move down through the chest, the belly, the lower back.  Wherever you find tightness, you don't have to fix it.  Just acknowledge it.  Say, silently — "I see you.  You're welcome here."

### PAUSE 12s

[reflective] There's nothing to do right now.  Nowhere to be.  Just this breath.  Just this moment.  And then the next one.

### PAUSE 15s

[soft] [slowly] When you're ready, begin to notice the sounds around you.  The weight of your body in the room.  Wiggle your fingers and toes, softly.

### PAUSE 4s

[warmly] [slowly] And whenever you're ready… gently open your eyes.  Carry this stillness with you, into whatever comes next.

### PAUSE 3s
```

---

## Part 6 — Common mistakes and what to do instead

| Mistake | Why it breaks | Do this instead |
|---|---|---|
| `[long pause]` written inline 5 times in a row | Causes v3 prosody artifacts; pause length is unpredictable | Use `### PAUSE 8s` on its own line |
| `<break time="5s"/>` SSML tag | v2 only, capped at 3 s; ignored on v3 | Use `### PAUSE 5s` |
| One giant 4,000-word paragraph | Far above the recommended 800-char limit for maintaining vocal warmth; will be sentence-split, losing your intended breath points | Break into paragraphs of 4–8 sentences |
| Tone tag only on paragraph 1 | Tags fade across paragraphs in v3; later paragraphs lose the soft register | Start every paragraph with a tone tag |
| Stage directions like `(softly)` or `*pauses*` | The model speaks them aloud | Use `[soft]` or `### PAUSE Xs` |
| `[whispers]` for an entire 15-minute meditation | Whispered TTS is fatiguing and unintelligible at length | Use `[soft]` as the default; `[whispers]` for short intimate beats |
| Numbered lists ("1. Notice your breath. 2. …") | The model literally says "one, two" | Write as prose: *"First… notice your breath. Then…"* |
| Acronyms and numbers ("Take a 4-7-8 breath") | Pronounced inconsistently | Spell out: *"Breathe in for four counts… hold for seven… release for eight."* |
| `[shouts]`, `[angry]`, `[laughs]` | Wrong register for meditation | See "Tags to avoid" in Part 2 |
| Excessive `…` (every line) | Sounds drugged or distracted | 3–4 per paragraph max |
| ALL CAPS for whole sentences | Reads as shouting | Use sparingly for emphasis on 1–2 words |

---

Following the rules above precisely, write me a **10-minute guided meditation** for **calming end-of-day anxiety**. Use a **warm, gentle, slightly intimate** tone. Include 2–3 conscious-breath cues, a brief body scan, and a closing invitation. Target ~1,200 spoken words. Output plain text only, ready to paste — no preamble, no markdown, no commentary.
