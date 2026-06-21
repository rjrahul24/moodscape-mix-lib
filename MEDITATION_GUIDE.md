# Meditation Script Guide — for use with the Meditation Audio Mixer

---

## Part 1 — Hard rules the LLM must follow

These are non-negotiable. The Mixer's parser depends on them.

1. **Output is plain text only.** No markdown headings, no bullets, no preamble like *"Here is your script…"*, no closing remarks. Just the meditation, ready to paste.
2. **Every line is separated by a blank line.** After each line of text, press enter **twice** to create a blank line before the next line. This is how the Mixer splits text into TTS chunks. Consecutive lines without a blank line between them get merged into a single chunk, which makes them sound rushed and reduces the calm pacing.

   ✅ **Correct:**
   ```
   [warmly] Welcome to tonight's sleep journey.

   Take a few moments to find your perfect resting position.
   ```

   ❌ **Wrong:**
   ```
   [warmly] Welcome to tonight's sleep journey.
   Take a few moments to find your perfect resting position.
   ```

3. **All pauses use `[pause for X seconds]`** on a line by itself, surrounded by blank lines. These are *programmatic silence* — they cost nothing and are exact to the millisecond. Use them for any pause **longer than ~2 seconds**. Do NOT use `### PAUSE Xs` or any other pause format.

   ✅ **Correct:**
   ```
   [soft] Notice the weight of your body.

   [pause for 5 seconds]

   [gentle] Feel the support beneath you.
   ```

   ❌ **Wrong:**
   ```
   [soft] Notice the weight of your body.

   ### PAUSE 5s

   [gentle] Feel the support beneath you.
   ```

4. **Short pauses (≤ 2 s) use punctuation, not tags.** Specifically:
   - `…` (ellipsis) — soft hesitation, breath-length pause, ~0.5–1 s
   - `—` (em-dash, surrounded by spaces) — stronger break, ~1–1.5 s
   - `.` (period) — sentence boundary, natural pause
   - `,` (comma) — slight in-line pause

5. **Audio tags use square brackets**, lower-case, at the position where the effect should start. Examples: `[soft]`, `[whispers]`, `[exhales]`. Tags **never** appear inside another tag.

6. **Every line starts with a tone or pacing tag.** The first token of each line must be a tone-setting or pacing tag like `[soft]`, `[calm]`, `[gentle]`, `[slow]`, `[very slow]`, `[serene]`, `[warmly]`, or `[whispers]`. Tone and pacing tags fade within v3, so they **must be re-asserted on every line** to keep the voice slow, calm, and meditative throughout.

7. **Re-assert pacing tags every 2–3 lines.** Even if you use the same tag consecutively, write it again. Vary the tags naturally (e.g. `[soft]` → `[gentle]` → `[slow]` → `[very gentle]` → `[calm]`). The goal is to **constantly remind the model to stay slow and calm**. Without frequent tag re-assertion, the voice drifts toward a faster, narrator-like register over time.

   ✅ **Correct — tags on every line, varied naturally:**
   ```
   [warmly] Welcome to tonight's sleep journey.

   [soft] Take a few moments to find your perfect resting position.

   [gentle] Let the day begin to fall away from you.

   [pause for 5 seconds]

   [slow] Feel the weight of your body… settling into the surface beneath you.

   [very gentle] There's nowhere you need to be right now.

   [soft] Nothing you need to do.

   [pause for 8 seconds]
   ```

   ❌ **Wrong — missing tags, no blank lines:**
   ```
   Welcome to tonight's sleep journey.
   Take a few moments to find your perfect resting position.
   Let the day begin to fall away from you.
   ```

8. **Per-line length: 1–3 sentences, 60–200 characters.** Keep each line short and focused — one thought per line. This keeps the voice intimate and prevents the model from speeding up mid-chunk. Lines above 800 chars risk vocal drift.

9. **No `<break>` tags, no SSML, no `[long pause]` repeated multiple times.** Pauses go through `[pause for X seconds]` only. ElevenLabs explicitly warns that `<break>` and repeated pause tags cause speed-ups and audio artifacts.

10. **No stage directions outside tags.** Don't write *"(softly)"* or *"--in a quiet voice--"*. The model only obeys things inside `[…]` and `[pause for]`.

11. **Total length budget:** 5-min meditation ≈ 600 spoken words ≈ 3,500 characters of speech. 10-min ≈ 1,200 words ≈ 7,000 chars. 20-min ≈ 2,200 words ≈ 13,000 chars. Add pause time on top.

---

## Part 2 — Audio tag reference (verified for Eleven v3)

Place the tag **just before** the speech you want it to affect. Tags are case-insensitive but lower-case keeps the script readable.

### Tone / delivery tags (use at the start of EVERY line)

These tags control the voice's emotional register and pacing. **Rotate through them** to keep the delivery varied yet consistently calm.

| Tag | Effect | Best for |
|---|---|---|
| `[soft]` | Warm, low-volume delivery. The workhorse tone for guided meditation. | Default tone tag |
| `[gentle]` | Tender, careful, unhurried. | Instructions, transitions, body-scan cues |
| `[slow]` | Noticeably reduces pace within the line. | Breathing cues, closing lines, emphasis |
| `[very slow]` | Deeply slowed, spacious delivery. | Deep relaxation, final wind-down, sleep meditations |
| `[very gentle]` | Extremely soft and careful. | Vulnerable moments, intimate affirmations |
| `[calm]` | Even, measured, grounded. | Body-scan, focus meditations |
| `[serene]` | Spacious, unhurried, slightly bright. | Open-awareness, nature visualizations |
| `[warmly]` | Friendly, embracing. | Welcomes, affirmations, lovingkindness |
| `[whispers]` | Hushed, intimate, almost breathy. | Sleep meditations, vulnerable moments |
| `[reassuringly]` | Steady, parental. | Anxiety meditations, "it's okay…" lines |
| `[slowly]` | Reduces pace within the line. | Counting breaths, closing lines |
| `[reflective]` | Inward, thoughtful. | Reframing, self-inquiry prompts |
| `[inner monologue]` | Quieter, more private register. | Visualization, dream-like passages |

**Recommended rotation for a 10-minute meditation:**
`[warmly]` → `[soft]` → `[gentle]` → `[calm]` → `[slow]` → `[soft]` → `[very gentle]` → `[gentle]` → `[slow]` → `[very slow]` → `[soft]` → `[warmly]`

### Breath / body (use mid-line, near the verb)

| Tag | What it produces |
|---|---|
| `[exhales]` | Audible out-breath. Single use per sentence. |
| `[inhales]` | Audible in-breath. |
| `[breathes]` | A complete breath cycle. |
| `[sighs]` | A relaxed, slow sigh. Strong after a pause. |
| `[breathing heavily]` | Use sparingly — only for grounding/embodied moments. |
| `[yawns]` | A real yawn. Strong for sleep meditations near the end. |
| `[swallows]` | Subtle. Useful for naturalness, but use rarely. |

### Pause / pacing (only inside a line; for >2 s use `[pause for]`)

| Tag | What it produces |
|---|---|
| `[pauses]` | A brief in-line pause, similar to a comma but stronger. |
| `[dramatic pause]` | A noticeably longer in-line pause. Use sparingly. |

### Tags to AVOID for meditation

- `[laughs]`, `[giggles]`, `[snorts]`, `[crying]`, `[shouts]`, `[angry]`, `[sarcastic]` — wrong register.
- `[applause]`, `[gunshot]`, `[door creaks]`, `[explosion]` — wrong genre.
- Any "strong X accent" tag — drift in voice across chunks.

### How tags compose

You can stack two tags at the start of a line for compound delivery: `[soft][slowly]` or `[whispers][reflective]`. Don't stack more than two.

You can place a transient tag mid-line for a single beat: *"`[soft]` Notice the weight of your body, `[exhales]` settling."*

---

## Part 3 — Punctuation, pacing, and emphasis

Eleven v3 listens to punctuation more carefully than v2.

| Mark | Effect |
|---|---|
| `,` (comma) | Light in-line pause (~150 ms). Use generously for rhythm. |
| `.` (period) | Full sentence boundary, natural prosody drop. |
| `…` (ellipsis, single character) | Soft hesitation, ~0.5–1 s. The single most useful punctuation mark for meditation. Use *between thoughts within a sentence*. Don't overuse — two or three per line max. |
| ` — ` (em-dash with spaces) | Stronger break than ellipsis. Use for definitive pause inside a sentence. |
| Blank line | Full pause and prosody reset. **Required between every line.** |
| **CAPITALIZATION** | Emphasis. **Use for at most one or two words per line.** For meditation this is rare — usually you don't need it. |
| Repeated periods like `...` | Treated like an ellipsis. Prefer the single character `…`. |

**Two spaces after a sentence** (e.g. *"Welcome.  Find a comfortable position."*) is a hint to the model to take a slightly longer breath at the sentence break. Optional but helpful.

---

## Part 4 — Pacing for slow, relaxing delivery

Professional meditation apps (Headspace, Calm) deliver at **80–100 effective WPM** — far slower than normal speech (~150 WPM). The Mixer achieves this through **three automatic layers** plus your script-writing choices:

### What the system does automatically (you don't need to)

1. **API speed = 0.80** — the slowest clean setting before v3 starts warping vowels.
2. **`[slowly]` tag injected on every chunk** — even if your line starts with `[calm]` or `[whispers]`, the system auto-appends `[slowly]` for pacing. You do NOT need to write `[slowly]` yourself (but adding `[slow]` or `[very slow]` gives extra emphasis).
3. **Inter-sentence pause injection** — the system automatically inserts a soft ellipsis pause (`…`) between sentences that don't already have one. This adds ~0.5–1 s of breathing room at every sentence boundary.

### What YOU control through the script

The biggest lever for pacing is **how you write**, not how fast the voice speaks.

**Keep each line short — 1–3 sentences.** Each line = one thought. Long, complex lines feel rushed even at a slow speed.

```
❌  Notice the weight of your body pressing down into the chair and feel the support beneath you.

✅  [soft] Notice the weight of your body.

✅  [gentle] Feel the support beneath you.
```

**Use `[pause for X seconds]` generously.** The system doubles all pause durations by default (`pause_scale=2.0`), so `[pause for 4 seconds]` becomes 8 seconds of silence. Use pauses between every breathing cue and between major sections.

**Add tone/pacing tags on every line.** This is the single most important thing you can do to keep the voice slow and calm. Without tags, v3 drifts into a faster, narrator-like register after a few chunks.

**Use ellipses (`…`) for mid-sentence breath pauses:**

```
[slow] Take a slow breath in… filling the chest… then the belly.
```

**Use em-dashes (` — `) for stronger breaks:**

```
[gentle] The jaw — let it unclench.  The shoulders — dropping away from the ears.
```

**Space your breathing cues.** Don't stack `[inhales]` and `[exhales]` in the same sentence. Give each its own beat:

```
❌  Breathe in [inhales] and out [exhales] slowly.

✅  [calm] Breathe in… [inhales]

[pause for 4 seconds]

[soft] And let it go.  [exhales]
```

### Effective WPM guide

| Target feel | Spoken WPM | How to achieve |
|---|---|---|
| Conversational (too fast) | 120–150 | Long sentences, few pauses, no tags |
| Calm narration | 100–120 | Short sentences, some pauses |
| **Guided meditation** | **80–100** | Short lines with tags, generous `[pause for]`, ellipses |
| Deep relaxation / sleep | 60–80 | Very sparse text, long `[pause for 10 seconds]` – `[pause for 20 seconds]`, `[whispers]`, `[very slow]` |

---

## Part 5 — Structural template for a guided meditation

Use this skeleton. Numbers in parentheses are typical durations for a 10-minute meditation; scale linearly for other lengths.

```
[warmly] Welcome.  Find a comfortable position — somewhere you can settle in, fully supported.

[soft] Let the chair, the cushion, or the floor hold your weight.

[pause for 3 seconds]

[gentle] When you're ready… softly close your eyes.

[calm] Or simply let your gaze rest on a point in front of you, unfocused.

[soft] [exhales] And let yourself arrive here, just as you are.

[pause for 5 seconds]

[calm] Take a slow breath in through the nose… [inhales]

[soft] …filling the chest, then the belly.

[gentle] And then a long, easy exhale out through the mouth.  [exhales]

[pause for 4 seconds]

[slow] Again.  In through the nose… [inhales]

[very gentle] …pause at the top…

[soft] and out, releasing whatever you're holding.  [exhales]

[pause for 6 seconds]

[gentle] Now let the breath find its own rhythm.

[soft] You don't need to control it.

[slow] Just notice — the rise, the fall, the small pause between.

[pause for 10 seconds]

[calm] Begin to scan your body, top down.

[soft] Notice the crown of your head.

[gentle] The forehead, soft.

[slow] The jaw — let it unclench.

[soft] The shoulders, dropping away from the ears.  [exhales]

[pause for 8 seconds]

[gentle] Move down through the chest, the belly, the lower back.

[very gentle] Wherever you find tightness, you don't have to fix it.

[soft] Just acknowledge it.

[calm] Say, silently — "I see you.  You're welcome here."

[pause for 12 seconds]

[reflective] There's nothing to do right now.

[soft] Nowhere to be.

[very slow] Just this breath.  Just this moment.  And then the next one.

[pause for 15 seconds]

[soft] When you're ready, begin to notice the sounds around you.

[slow] The weight of your body in the room.

[gentle] Wiggle your fingers and toes, softly.

[pause for 4 seconds]

[warmly] And whenever you're ready… gently open your eyes.

[soft] Carry this stillness with you, into whatever comes next.

[pause for 3 seconds]
```

**For sleep meditations**, replace the closing with a "drift off" arc: longer pauses (10–20 s), `[whispers]` tone, more `[yawns]` and `[exhales]`, `[very slow]`, no "open your eyes" instruction.

---

## Part 6 — Common mistakes and what to do instead

| Mistake | Why it breaks | Do this instead |
|---|---|---|
| `### PAUSE 5s` syntax | Deprecated; use the `[pause for]` format instead | Use `[pause for 5 seconds]` on its own line |
| `[long pause]` written inline 5 times in a row | Causes v3 prosody artifacts; pause length is unpredictable | Use `[pause for 8 seconds]` on its own line |
| `<break time="5s"/>` SSML tag | v2 only, capped at 3 s; ignored on v3 | Use `[pause for 5 seconds]` |
| Lines without blank lines between them | Get merged into one chunk — loses pacing, sounds rushed | Always separate lines with a blank line (press enter twice) |
| Lines without a tone/pacing tag | Voice drifts to narrator register after a few chunks | Start every line with `[soft]`, `[gentle]`, `[slow]`, `[calm]`, etc. |
| One giant paragraph of 4+ sentences | Far above the recommended line length; causes vocal drift | Break into separate lines with blank lines between them |
| Stage directions like `(softly)` or `*pauses*` | The model speaks them aloud | Use `[soft]` or `[pause for X seconds]` |
| `[whispers]` for an entire 15-minute meditation | Whispered TTS is fatiguing and unintelligible at length | Use `[soft]` as the default; `[whispers]` for short intimate beats |
| Numbered lists ("1. Notice your breath. 2. …") | The model literally says "one, two" | Write as prose: *"First… notice your breath. Then…"* |
| Acronyms and numbers ("Take a 4-7-8 breath") | Pronounced inconsistently | Spell out: *"Breathe in for four counts… hold for seven… release for eight."* |
| `[shouts]`, `[angry]`, `[laughs]` | Wrong register for meditation | See "Tags to avoid" in Part 2 |
| Excessive `…` (every line) | Sounds drugged or distracted | 2–3 per line max |
| ALL CAPS for whole sentences | Reads as shouting | Use sparingly for emphasis on 1–2 words |
| Using the same tag for every single line | Monotonous; model may start ignoring it | Rotate through `[soft]`, `[gentle]`, `[slow]`, `[calm]`, `[very gentle]`, etc. |

---

## Part 7 — Quick formatting checklist

Before pasting your script into the Mixer, verify:

- [ ] Every line is separated by a blank line (double-enter)
- [ ] Every line starts with a tone or pacing tag (`[soft]`, `[gentle]`, `[slow]`, etc.)
- [ ] Tags are varied — rotate through at least 4–5 different tags
- [ ] Pauses use `[pause for X seconds]` format only
- [ ] Each line has 1–3 sentences (60–200 characters)
- [ ] Ellipses (`…`) used for mid-sentence breaths, 2–3 per line max
- [ ] No markdown, no SSML, no stage directions outside `[…]`
- [ ] Total word count matches target duration (see Part 1, rule 11)

---

Following the rules above precisely, write me a **10-minute guided meditation** for **calming end-of-day anxiety**. Use a **warm, gentle, slightly intimate** tone. Include 2–3 conscious-breath cues, a brief body scan, and a closing invitation. Target ~1,200 spoken words. Output plain text only, ready to paste — no preamble, no markdown, no commentary.
