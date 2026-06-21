# Sleep Story Script Guide — for use with the Meditation Audio Mixer

---

## Part 1 — Hard rules the LLM must follow

These are non-negotiable. The Mixer's parser depends on them.

> **How a sleep story differs from a guided meditation:**
>
> A guided meditation *directs the listener's attention and nervous system* with frequent instructions and long, frequent pauses — the silence is where the work happens. A sleep story *gently distracts* — one continuous narrated story carries the listener toward sleep; the words themselves are the point, and pauses are minimal. Think of it as a warm, slow bedtime story for adults: soft, safe, unhurried, with almost no silence.
>
> Key contrasts:
> - **Fewer and shorter pauses** — a 10-minute meditation might have 8–12 explicit pauses; a 10-minute sleep story should have only 3–5 short ones.
> - **Longer continuous stretches of narration** — the voice flows smoothly with fewer hard stops.
> - **Setting over instruction** — meditations say "notice your breath"; sleep stories say "the path curved gently through the meadow."
> - **Same softness, less silence** — the vocal delivery is equally warm and unhurried, just with far less empty space.

1. **Output is plain text only.** No markdown headings, no bullets, no preamble like *"Here is your script…"*, no closing remarks. Just the story, ready to paste.
2. **Every line is separated by a blank line.** After each line of text, press enter **twice** to create a blank line before the next line. This is how the Mixer splits text into TTS chunks. Consecutive lines without a blank line between them get merged into a single chunk, which makes them sound rushed and reduces the calm pacing.

   ✅ **Correct:**
   ```
   [warm] The path curved gently through the meadow.

   [soft] Tall grasses swayed on either side, catching the last light.
   ```

   ❌ **Wrong:**
   ```
   [warm] The path curved gently through the meadow.
   [soft] Tall grasses swayed on either side, catching the last light.
   ```

3. **All pauses use `[pause for X seconds]`** on a line by itself, surrounded by blank lines. These are *programmatic silence* — they cost nothing and are exact to the millisecond. Use them only at genuine scene shifts. Do NOT use `### PAUSE Xs` or any other pause format.

   ✅ **Correct:**
   ```
   [soft] The river opened into a wide, still lake.

   [pause for 2 seconds]

   [gentle] Along the far shore, a cabin sat among the pines.
   ```

   ❌ **Wrong:**
   ```
   [soft] The river opened into a wide, still lake.

   ### PAUSE 2s

   [gentle] Along the far shore, a cabin sat among the pines.
   ```

4. **Short pauses (≤ 2 s) use punctuation, not tags.** Specifically:
   - `…` (ellipsis) — soft hesitation, breath-length pause, ~0.5–1 s
   - `—` (em-dash, surrounded by spaces) — stronger break, ~1–1.5 s
   - `.` (period) — sentence boundary, natural pause
   - `,` (comma) — slight in-line pause

5. **Audio tags use square brackets**, lower-case, at the position where the effect should start. Examples: `[soft]`, `[whispers]`, `[exhales]`. Tags **never** appear inside another tag.

6. **Every line starts with a tone or pacing tag.** The first token of each line must be a tone-setting or pacing tag like `[soft]`, `[calm]`, `[gentle]`, `[slow]`, `[very slow]`, `[serene]`, `[warmly]`, `[warm]`, or `[whispers]`. Tone and pacing tags fade within v3, so they **must be re-asserted on every line** to keep the voice slow, calm, and story-like throughout.

7. **Re-assert pacing tags every 2–3 lines.** Even if you use the same tag consecutively, write it again. Vary the tags naturally (e.g. `[soft]` → `[warm]` → `[gentle]` → `[calm]` → `[serene]`). The goal is to **constantly remind the model to stay slow and soft**. Without frequent tag re-assertion, the voice drifts toward a faster, narrator-like register over time.

   ✅ **Correct — tags on every line, varied naturally:**
   ```
   [warm] The evening air carried the scent of pine and damp earth.

   [soft] A narrow trail wound downhill, cushioned with fallen needles.

   [gentle] Each step was quiet, unhurried.

   [pause for 2 seconds]

   [serene] Below, the valley opened wide, golden in the late sun.

   [calm] A stream threaded through the grass, barely moving.

   [soft] You could hear it only when the breeze paused.
   ```

   ❌ **Wrong — missing tags, no blank lines:**
   ```
   The evening air carried the scent of pine and damp earth.
   A narrow trail wound downhill, cushioned with fallen needles.
   Each step was quiet, unhurried.
   ```

8. **Per-line length: 1–2 sentences, 60–200 characters.** Keep each line short and focused — one image per line. This keeps the voice intimate and prevents the model from speeding up mid-chunk. Lines above 800 chars risk vocal drift.

9. **No `<break>` tags, no SSML, no `[long pause]` repeated multiple times.** Pauses go through `[pause for X seconds]` only. ElevenLabs explicitly warns that `<break>` and repeated pause tags cause speed-ups and audio artifacts.

10. **No stage directions outside tags.** Don't write *"(softly)"* or *"--in a quiet voice--"*. The model only obeys things inside `[…]` and `[pause for]`.

11. **Total length budget:** A sleep story targets ~110 spoken words per minute. 10-min story ≈ 1,100 words ≈ 6,500 characters of speech. 15-min ≈ 1,650 words ≈ 9,500 chars. 20-min ≈ 2,200 words ≈ 13,000 chars. Add pause time on top (but remember: pause time is minimal).

---

## Part 2 — Audio tag reference (verified for Eleven v3)

Place the tag **just before** the speech you want it to affect. Tags are case-insensitive but lower-case keeps the script readable.

### Tone / delivery tags (use at the start of EVERY line)

These tags control the voice's emotional register and pacing. **Rotate through them** to keep the delivery varied yet consistently soft and warm.

| Tag | Effect | Best for |
|---|---|---|
| `[soft]` | Warm, low-volume delivery. The workhorse tone for sleep stories. | Default tone tag |
| `[gentle]` | Tender, careful, unhurried. | Descriptions of small details, transitions |
| `[slow]` | Noticeably reduces pace within the line. | Scene shifts, emphasis |
| `[very slow]` | Deeply slowed, spacious delivery. | Final third wind-down, trailing-off passages |
| `[very gentle]` | Extremely soft and careful. | Intimate, close-feeling moments |
| `[calm]` | Even, measured, grounded. | Steady narration, landscape descriptions |
| `[serene]` | Spacious, unhurried, slightly bright. | Open vistas, nature imagery |
| `[warmly]` / `[warm]` | Friendly, embracing. | Opening lines, welcoming the listener |
| `[whispers]` | Hushed, intimate, almost breathy. | Final wind-down, last few lines before sleep |
| `[slowly]` | Reduces pace within the line. | Slow-motion details, closing passages |
| `[inner monologue]` | Quieter, more private register. | Dream-like passages, internal observations |

**Recommended rotation for a 10-minute sleep story:**
`[warm]` → `[soft]` → `[gentle]` → `[calm]` → `[serene]` → `[soft]` → `[gentle]` → `[slow]` → `[very gentle]` → `[soft]` → `[very slow]` → `[whispers]`

### Breath / body (use sparingly, to open a paragraph)

| Tag | What it produces |
|---|---|
| `[exhales]` | Audible out-breath. Use to open a paragraph for a beat of naturalness. |
| `[sighs]` | A relaxed, slow sigh. Strong at the start of a paragraph to signal settling. |
| `[yawns]` | A real yawn. Use once or twice near the end to mirror the listener's drowsiness. |

For sleep stories, breath tags should be **rare** — perhaps 2–3 in the whole story, usually to open a new paragraph. Unlike meditation, breath is not cued; it just adds warmth.

### Pause / pacing (only inside a line; for >2 s use `[pause for]`)

| Tag | What it produces |
|---|---|
| `[pauses]` | A brief in-line pause, similar to a comma but stronger. |

### Tags to AVOID for sleep stories

- `[laughs]`, `[giggles]`, `[snorts]`, `[crying]`, `[shouts]`, `[angry]`, `[sarcastic]` — wrong register.
- `[applause]`, `[gunshot]`, `[door creaks]`, `[explosion]` — wrong genre.
- `[dramatic pause]` — too theatrical; use punctuation instead.
- `[inhales]`, `[breathing heavily]` — meditation register; sleep stories don't cue breath.
- Any "strong X accent" tag — drift in voice across chunks.

### How tags compose

You can stack two tags at the start of a line for compound delivery: `[soft][slowly]` or `[whispers][very slow]`. Don't stack more than two.

You can place a transient tag mid-line for a single beat: *"`[soft]` The cabin door was warm to the touch, `[sighs]` and the hinges barely whispered."*

---

## Part 3 — Narrative craft

### Story shape

A sleep story follows **one simple character or vantage point on an unhurried journey**. Setting over plot. The listener is either the character ("you walk…") or a close observer. There is:

- **No tension, no stakes, no conflict.** Nothing needs to be solved.
- **No dramatic reveals or twists.** Predictability is a feature.
- **No dialogue.** Quoted speech lifts the energy and breaks the drowsy register.
- **No direct questions to the listener.** Questions activate the mind; the goal is to quiet it.

Everything in the story is **safe, calm, and pleasant**. The world is gentle and welcoming.

### The progressive calm arc

Structure the story in three broad phases:

1. **First third — Arriving** (mildly active). The character arrives somewhere or notices the setting. Sensory details are vivid but gentle: colours, textures, scents, ambient sounds. Sentences may have mild motion (walking, looking around).
2. **Middle third — Settling** (slowing). Motion decreases. The character finds a resting place — a bench, a blanket, a boat drifting on still water. Details become softer and simpler. Sentences shorten.
3. **Final third — Trailing off** (near stillness). Almost no action. Soft repetition of images. Sentences become fragments. The narrative simply fades, like a voice growing more distant. No formal ending — the story dissolves.

### Sensory imagery

- **One image per sentence.** Don't stack multiple sense-impressions in a single line.
- Favour **gentle, safe imagery**: warm light, soft fabric, still water, slow rain, birdsong fading, distant bells, candlelight, the smell of earth after rain.
- Avoid anything that could be **startling, unpleasant, or mentally activating**: sudden sounds, bright light, cold, insects, heights, crowds, technology, deadlines.

---

## Part 4 — Pacing and sentence structure

This is what makes delivery slow. Target **~110 spoken words per minute** — slower than conversation (~150 WPM) but with less silence than meditation (~80–100 WPM with pauses).

**Keep sentences short: 5–20 words, one image each.** Use commas to break sentences into breath-sized phrases.

```
❌  The path wound through the meadow and crossed over a narrow stream where the water was clear and you could see smooth stones on the bottom.

✅  [soft] The path wound through the meadow.

✅  [gentle] It crossed a narrow stream, the water clear and unhurried.

✅  [calm] Smooth stones lined the bottom, pale as eggshell.
```

**Avoid compound and run-on sentences.** They make the model speed up to get through the material. If you hear an "and" or a "but" in the middle, consider splitting the sentence in two.

**Use ellipses (`…`) for soft mid-sentence breathing:**

```
[soft] The light moved slowly across the ceiling… warm, golden, familiar.
```

**Use em-dashes (` — `) for gentle breaks:**

```
[gentle] A single bird called — far away — and then was quiet.
```

---

## Part 5 — Pauses (fewer and shorter than meditation)

Sleep stories use **far fewer explicit pauses** than meditations. The continuous flow of narration is what lulls the listener — silence wakes the mind.

### Guidelines

- Use `[pause for 1 second]` or `[pause for 2 seconds]` only at **genuine scene shifts** — when the story moves to a new location or a new phase of the calm arc.
- **Do NOT pause after most lines.** The blank line between lines already provides a natural prosody reset.
- **Rely on commas, `…`, and ` — ` for soft in-line breathing** instead of explicit pause lines.
- A 10-minute sleep story should have roughly **3–5 explicit pauses**, each 1–2 seconds.

### Important: the app handles the wind-down for you

The app automatically **lengthens pauses gradually toward the end** of the story (a built-in wind-down ramp). This means the few short pauses you write in the final third will be stretched automatically. **Do NOT stack long explicit pauses** (e.g. `[pause for 8 seconds]`, `[pause for 10 seconds]`) — they will be amplified by the ramp and create uncomfortably long silences. Write short pauses (1–2 seconds) and let the app handle the deepening.

### What the system does automatically (you don't need to)

1. **API speed = 0.80** — the slowest clean setting before v3 starts warping vowels.
2. **`[calm][soft]` tone preset re-asserted at chunk boundaries** — the system automatically prepends `[calm][soft]` to any chunk that doesn't already start with a tag, keeping the voice consistently soft and grounded. You do NOT need to write this prefix yourself (but using `[slow]` or `[very slow]` gives extra emphasis).
3. **Inter-sentence pause injection** — the system automatically inserts a soft ellipsis pause (`…`) between sentences that don't already have one.
4. **Progressive pause ramp** — pause durations are automatically lengthened toward the end of the story, deepening the wind-down without script changes.

---

## Part 6 — Punctuation, pacing, and emphasis

Eleven v3 listens to punctuation more carefully than v2.

| Mark | Effect |
|---|---|
| `,` (comma) | Light in-line pause (~150 ms). Use generously for rhythm. |
| `.` (period) | Full sentence boundary, natural prosody drop. |
| `…` (ellipsis, single character) | Soft hesitation, ~0.5–1 s. The most useful punctuation mark for sleep stories — use it *between images within a sentence*. Don't overuse — two or three per line max. |
| ` — ` (em-dash with spaces) | Stronger break than ellipsis. Use for a definitive pause inside a sentence. |
| Blank line | Full pause and prosody reset. **Required between every line.** |
| **CAPITALIZATION** | Emphasis. **Use for at most one or two words per line.** For sleep stories this is very rare. |
| Repeated periods like `...` | Treated like an ellipsis. Prefer the single character `…`. |

**Two spaces after a sentence** (e.g. *"The candle flickered.  Then it was still."*) is a hint to the model to take a slightly longer breath at the sentence break. Optional but helpful.

---

## Part 7 — Worked example

Below is a short excerpt (12 lines) in the exact app syntax. Note: short sentences, leading tone tags, blank lines between every line, and only two `[pause for 2 seconds]` at scene shifts.

```
[warm] The train moved slowly through the hills, rocking gently on the rails.

[soft] Outside the window, the fields were gold and green, stretching to the horizon.

[gentle] The light was low now… amber, soft, fading.

[calm] You leaned against the window, the glass cool against your temple.

[pause for 2 seconds]

[serene] The train crossed a stone bridge over a river.

[soft] The water below was dark and still, catching the last colour of the sky.

[gentle] On the far bank, a row of trees stood motionless… their reflections perfect.

[slow] The rhythm of the rails was steady, steady, steady.

[pause for 2 seconds]

[very gentle] Your eyes grew heavy.

[soft] The fields blurred softly… the light dimmed… and everything was warm.
```

---

## Part 8 — Common mistakes and what to do instead

| Mistake | Why it breaks | Do this instead |
|---|---|---|
| `### PAUSE 5s` syntax | Deprecated; use the `[pause for]` format instead | Use `[pause for 2 seconds]` on its own line |
| `[pause for 8 seconds]` or longer | The app's wind-down ramp amplifies pauses toward the end; long explicit pauses become uncomfortably long silences | Keep pauses at 1–2 seconds; let the app ramp handle deepening |
| `<break time="5s"/>` SSML tag | v2 only, capped at 3 s; ignored on v3 | Use `[pause for 2 seconds]` |
| Lines without blank lines between them | Get merged into one chunk — loses pacing, sounds rushed | Always separate lines with a blank line (press enter twice) |
| Lines without a tone/pacing tag | Voice drifts to narrator register after a few chunks | Start every line with `[soft]`, `[gentle]`, `[slow]`, `[calm]`, etc. |
| Long compound sentences ("and… and… and…") | Make the model speed up to get through the material | Split into short, single-image sentences |
| Dialogue or direct questions | Activate the listener's mind; break the drowsy register | Use indirect narration: *"Someone had left a light on in the window"* |
| Tension, conflict, or dramatic reveals | Raise alertness — the opposite of sleep | Keep everything safe, calm, predictable |
| Stage directions like `(softly)` or `*pauses*` | The model speaks them aloud | Use `[soft]` or `[pause for X seconds]` |
| Pauses after every line | Too much silence; the listener wakes up between lines | Pause only at scene shifts (3–5 times per 10 minutes) |
| `[whispers]` for the entire story | Whispered TTS is fatiguing and unintelligible at length | Use `[soft]` as default; `[whispers]` for the final few lines only |
| Numbered lists ("1. The sky… 2. The trees…") | The model literally says "one, two" | Write as prose |
| Using the same tag for every single line | Monotonous; model may start ignoring it | Rotate through `[soft]`, `[gentle]`, `[slow]`, `[calm]`, `[serene]`, etc. |
| `[shouts]`, `[angry]`, `[laughs]` | Wrong register for sleep stories | See "Tags to avoid" in Part 2 |
| Excessive `…` (every line) | Sounds drugged or distracted | 2–3 per line max |
| ALL CAPS for whole sentences | Reads as shouting | Use sparingly for emphasis on 1–2 words |

---

## Part 9 — Quick formatting checklist

Before pasting your script into the Mixer, verify:

- [ ] Every line is separated by a blank line (double-enter)
- [ ] Every line starts with a tone or pacing tag (`[soft]`, `[gentle]`, `[slow]`, etc.)
- [ ] Tags are varied — rotate through at least 4–5 different tags
- [ ] Pauses use `[pause for X seconds]` format only
- [ ] Pauses are short (1–2 seconds) and infrequent (3–5 per 10 minutes)
- [ ] No long explicit pauses (the app's wind-down ramp handles deepening)
- [ ] Each line has 1–2 sentences (60–200 characters), one image per line
- [ ] Sentences are short (5–20 words) with no run-on compound structures
- [ ] Ellipses (`…`) used for mid-sentence breaths, 2–3 per line max
- [ ] No markdown, no SSML, no stage directions outside `[…]`
- [ ] No dialogue, no questions to the listener, no tension or conflict
- [ ] Story follows the progressive calm arc (arriving → settling → trailing off)
- [ ] Total word count matches target duration (~110 WPM; 10 min ≈ 1,100 words)

---

## Part 10 — Example prompt to give the LLM

Following the rules above precisely, write me a **10-minute sleep story** about **a quiet evening train journey through the countryside**. Use a **warm, soft, unhurried** tone. The listener is a passenger gazing out the window as the landscape slowly darkens. Follow the progressive calm arc: the first third notices details of the passing scenery, the middle third settles as the train slows, and the final third trails off into drowsy fragments. Target ~1,100 spoken words. Output plain text only, ready to paste — no preamble, no markdown, no commentary.

*(Customize the topic in bold; the LLM will generate a story matching your sleep-story rules.)*
