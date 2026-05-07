---
name: produce-feature-video
description: End-to-end workflow for producing a short product feature
  video using this repo's tools — narration script, TTS audio, hand-driven
  Playwright recording, cursor + click compositing, smart zoom-ins via
  DaVinci Resolve, final edit. Use when the user wants to record a new
  walkthrough video of a UI feature.
---

# Producing a feature video

This is an agent-facing skill. You drive the pipeline; the user
contributes the brief, the recording (clicking through their app live to
the narration), and the final polish in Resolve. Hand off to the user
explicitly at the points that need them.

The output of a run is a finished walkthrough video. Every routine step
(script drafting, cue annotation, zoom-region planning, cursor sprite,
click rings, Resolve assembly, zoom keyframes) is yours.

## Per-run folder

All artifacts for one video live in `runs/<slug>/`. `runs/` is
gitignored. Every script in this repo accepts `--run <slug>` and
resolves paths from there. Pick `<slug>` from the brief on the first
turn; confirm with the user before creating the folder. Use
kebab-case, short and descriptive (`provider-setup`, `agent-onboarding`).

Files inside `runs/<slug>/`:

```
description.md       # the brief the user gave you
exploration.md       # your UI map from step 2
script.md            # narration with {{cue}} markers (source of truth)
zoom-proposal.json   # your pre-recording zoom plan
speech.mp3           # TTS output (or user-supplied)
raw.mov              # screencast (after recording)
cursor.mov           # cursor track (after compositing)
click.mov            # click-ring track (after compositing)
events.json          # click + move events with timing
final.mp4            # quick-reference composite preview
```

## Tools you'll invoke

- `pnpm tts --run <slug>` — TTS narration mp3 from the script
- `pnpm record-manual <url> --run <slug>` — opens browser; user clicks
  through to narration; logs `events.json` + `raw.mov`
- `pnpm assemble --run <slug>` — composites cursor + click rings
- `python3 resolve/to-resolve.py --run <slug>` — Resolve timeline assembly
- `python3 resolve/apply-zoom-proposal.py --run <slug>` — keyframes the
  V1 compound clip from `zoom-proposal.json` + actual click times in
  `events.json`
- `python3 resolve/add-zooms.py --run <slug>` — heuristic fallback that
  groups clicks by cluster instead of using a proposal. Kept for cases
  where the proposal pipeline doesn't fit; not the default

DaVinci Resolve **Studio** is required (Free version doesn't expose
Fusion scripting).

## The flow

### 1. Take the brief

Ask the user, in one turn:

- What feature/workflow does this video demonstrate? Who's the audience?
- The URL of the running app, or how to start it locally.
- Any access notes (login, fixtures, environment).

Write the answer to `runs/<slug>/description.md`. Confirm the slug.

### 2. Explore the app

Drive the app with the Playwright MCP. **Resize the browser to the
recorder's target viewport before capturing any coordinates** — read
`config.viewport` from `src/shared/config.ts` (default 1920×1080) and
call `browser_resize` to match. Bboxes captured at any other size are
not transferable to the recording, so any `rect_css` in the proposal
needs to be in recorder-viewport CSS pixels.

Walk the path the demo will follow. Capture:

- The route(s) involved.
- The aria-label or id of every element you'd click in a demo of this
  feature. These become cue names later — copy them verbatim.
- The viewport regions where the action happens (top bar? left
  sidebar? main pane?). Note bbox approximations in CSS pixels.
- Any state that needs setup before recording (clean account, seeded
  data, a particular page).

If the source code is local, read it too — it's often faster than
clicking around to learn the UI.

Write a tight `runs/<slug>/exploration.md`: route → action → element
identifier → region note. One paragraph or table per scene the demo
covers.

If Playwright isn't available (sandboxed env, auth wall, app not
running), tell the user explicitly and ask for screenshots + a list of
clickable elements with their aria-labels. Don't guess.

### 3. Draft the script

Write narration whose audience is the **video viewer**, not the
recorder. The script's job is to teach what the feature does and why
it matters. Pacing for clicks is a side-effect of writing well, not
the goal.

Save to `runs/<slug>/script.md`. Tips:

- Write for the ear. Short sentences. Read aloud as you check.
- One idea per sentence. TTS garbles long clauses.
- Roughly: each visible UI moment ≈ one short sentence ("now the
  agents page", "click providers"). The recorder will pace clicks to
  the narration, so the click rhythm follows the sentence rhythm.

Iterate with the user. Don't move on until they confirm the script.

### 4. Annotate cues

Re-write `script.md` with `{{cue-name}}` markers at every visible UI
moment — every click the user will make, plus any non-click beats you
want to anchor a zoom on (e.g. a result appearing).

**Use the actual `aria-label` or `id` from your exploration as the cue
name** when one exists. Lowercase, hyphens or underscores. This is the
single most important rule in this skill: it makes cue→click binding
self-verifying.

```
First, open the {{providers-tab}}. Paste your key into the
{{api-key-input}} and click {{test-button}}. {{success-banner}}
```

If a target has no useful label (icon button without aria-label, etc.),
invent a descriptive cue (`{{primary-cta}}`) and note in
`exploration.md` what it points to.

The TTS strips `{{cues}}` automatically; you don't need a separate
"cue-stripped" file.

### 5. Plan zoom regions

Write `runs/<slug>/zoom-proposal.json` describing where the camera
should push in. The schema:

```json
{
  "viewport": { "width": 1920, "height": 1080 },
  "regions": [
    {
      "id": "providers-form",
      "anchor_cues": ["api-key-input", "test-button"],
      "rect_css": { "x": 720, "y": 280, "width": 480, "height": 240 },
      "zoom": 1.5,
      "pre_ms": 300,
      "hold_ms": 400,
      "post_ms": 400,
      "rationale": "Form fill — keep frame on the inputs while the
                    surrounding chrome stays constant."
    }
  ]
}
```

Field semantics:

- `anchor_cues`: ordered list of cue names that this region covers. The
  region runs from the first anchor's click to the last anchor's click,
  plus the configured ramps. At least one cue per region.
- `rect_css`: optional. The interesting region in CSS pixels. If
  omitted, the applier centres on the mean of the anchors' click bbox
  centres (computed from `events.json` after recording).
- `zoom`: peak zoom factor. **Default 1.3** — safe for any region with
  surrounding content that changes (top-bar buttons whose click
  navigates, sidebar items whose click loads a new view). **Push to
  1.5 for tight forms** (login, single-input dialogs, modals). **Don't
  exceed 1.8** — anything tighter looks pixely on a 4K capture.
- `pre_ms` / `hold_ms` / `post_ms`: ramp-in / hold-at-peak / ramp-out
  durations in ms. Defaults 300 / 400 / 400.
- `rationale`: one sentence. Used by you to think clearly, also surfaced
  in applier output for the user to scan.

**Hard rules. The applier validates these and refuses to emit
keyframes if they're violated:**

1. **A region must span at least 2 s of click activity.** Anchor the
   region on cues at least 2 s apart in narration (or expect the
   applier to skip it). Quick double-clicks aren't a region — the
   camera barely arrives before it has to leave.
2. **Single-cue regions are skipped** unless `hold_ms` ≥ 1500. One
   click is a navigation moment; stay zoomed out so the viewer sees
   the whole page change.
3. **The Centre is clamped frame-fill.** Edge-of-screen regions get
   pulled toward the centre by exactly the amount needed to keep the
   source covering the output frame. No black gutter, ever.

**When NOT to propose a zoom region** — these belong wide:

- **Whole page is changing** — navigation, route change, big content
  swap. Zooming during a transition makes the viewer dizzy.
- **Cursor is travelling across the screen** to a new area. Zoom out,
  travel, zoom in fresh in the new region.
- **Narration describes the layout overall** ("the get-started bar,
  the sidebar, the main pane"). Wide shots beat tight shots.
- **User is passively watching** (a thinking indicator, content
  streaming).
- **The whole UI fits in the frame and matters as a whole** — a
  bottom action bar walk where the bar IS the layout.
- **Title screens, hero shots, outros**.

The user can edit `zoom-proposal.json` between this step and step 10,
or tweak transforms in Resolve afterward. Both are valid.

### 6. Generate audio

Try the canonical TTS first:

```sh
ELEVENLABS_API_KEY=… pnpm tts --run <slug>
```

Default voice is Brian (free tier). For a different free-tier voice,
pass the voice id as the second arg.

If the user wants a premium ElevenLabs voice (Library/shared voices
require a paid plan; the API can't access them on free tier), tell
them: *"Premium voices need to be generated in the ElevenLabs UI. Open
the script at `runs/<slug>/script.md`, copy it (the cues are
automatically read as plain text and shouldn't break narration but
strip them if they do), generate the audio, and save the file as
`runs/<slug>/speech.mp3`. Tell me when you're done."*

Listen-check before recording: read `speech.mp3` back if any sentence
sounds wrong, re-write that sentence in `script.md` and regenerate.
TTS prosody depends on punctuation.

### 7. Record the take

Tell the user to run, in their terminal:

```sh
pnpm record-manual <start-url> --run <slug>
```

(With `--run`, the recorder picks up `runs/<slug>/speech.mp3`
automatically if it exists.)

Then tell them:

- Put on headphones — the audio plays through the system, not into the
  recording.
- Make sure the app is in the demo's starting state (logged in, fixtures
  seeded, on the right page) — note the specific state from
  `exploration.md`.
- 5-second prep window from the first frame, then audio starts.
- Click decisively, paced to the narration. Pause briefly before clicks
  the narration emphasises ("…click {{test-button}}, *[pause]* green
  check").
- Hold for ~1 s after the last click, then close the browser window
  (Cmd+W or red ✕). Recording finalises automatically.
- If the take is fluffed, just close and re-run — takes are cheap.

After the recorder exits, `runs/<slug>/` will contain `raw.mov`,
`events.json`, and timings.

### 8. Composite cursor + clicks

Run:

```sh
pnpm assemble --run <slug>
```

Outputs `cursor.mov`, `click.mov`, and a quick-reference `final.mp4`.

### 9. Resolve part 1 — assemble the timeline

Tell the user:

> *"Open DaVinci Resolve Studio, create a new project (any name), then
> tell me when it's open. I'll set up the timeline."*

Once they confirm:

```sh
python3 resolve/to-resolve.py --run <slug>
```

This creates a timeline with V1 (raw), V2 (cursor), V3 (click) merged
into a compound clip, A1 (narration) at the right offset, and a marker
per click event.

If the script reports the compound wasn't created automatically, tell
the user:

> *"Select V1+V2+V3 in the Resolve timeline → right-click → New
> Compound Clip. Tell me when done — `add-zooms.py` and the proposal
> applier both need a single compound on V1."*

### 10. Resolve part 2 — apply zoom keyframes

Run:

```sh
python3 resolve/apply-zoom-proposal.py --run <slug>
```

This reads `zoom-proposal.json` + `events.json`, binds each region's
`anchor_cues` to actual click events (ordinal match — the Nth cue in
the script binds to the Nth click in events.json — verified against
each click's `label`), emits a Fusion comp with Transform/Size
keyframes for every valid region, and attaches it to the V1 compound
clip.

Watch the applier's log:

- **Verification mismatch** (cue's expected identifier ≠ actual click's
  label): the user clicked the wrong element, missed a click, or
  double-clicked. The applier still proceeds with ordinal match but
  warns. If the warning lists a clearly-wrong binding, tell the user
  and offer to re-record or hand-fix the proposal.
- **Region skipped: span too short**: bump anchor cues farther apart
  in narration, or accept that region as wide.

After the script runs:

- Scrub the timeline. Each region should pulse zoom around its
  anchor clicks.
- The user can delete individual Transforms in Fusion to remove a
  zoom they don't like, or hand-edit Size keyframes for one specific
  region.

### 11. Hand off final polish

Tell the user the timeline is ready, and that what's left for them:

- **Trim head and tail** to match the audio start/end.
- **Slip-edit** the compound clip a few frames if any click landed
  off-rhythm with the narration.
- **Add intro / outro** — title card, logo, end card.
- **Color** if needed (usually not).
- **Export**: Deliver page → H.264 mp4, Studio quality, 30 fps.

## Recovery / iteration

| Problem                                  | Fix                                                                                           |
|---|---|
| Recorder hangs after browser close       | Cmd+W in the browser; SIGINT (Ctrl+C) in the terminal also works                              |
| Voice sounds wrong on a phrase           | Reword the phrase in `script.md` and regenerate `speech.mp3`                                  |
| Click landed off-target                  | Re-record. Don't edit `events.json` — the binder will warn anyway                             |
| Zoom feels too aggressive                | Lower the region's `zoom` in `zoom-proposal.json`; raise `pre_ms`/`post_ms` for softer ramps  |
| A region got skipped you wanted zoomed   | Anchor it on cues farther apart in narration so the span clears 2 s; or lower the per-region `min_duration_ms` (proposal field) |
| Black gutter behind a clip               | Shouldn't happen — applier clamps Centre. If it does, re-run with `--clear`                   |
| Need a different language                | Translate `script.md`, regenerate `speech.mp3`. `events.json` is unchanged so the rest of the pipeline reuses the take |
| Resolve produces black with comp applied | Known fragile area in Fusion. Run `python3 resolve/add-zooms.py --basic --run <slug>` to verify the simple path works, then re-run the applier |

## Out of scope for v1

- **PNG-template framing** (raw video inset into a branded background).
  The user does this manually in Resolve after step 9.
- **Live demos**. Output is recorded video.
- **Substitute for tools like Clueso/Tella** — those are no-code GUI
  workflows. This is a programmable pipeline.

## Anti-patterns

- Don't write the script for the recorder ("now click X, now click Y").
  Write it for the viewer; clicks fall out of good narration.
- Don't bypass the cue convention. If you can't think of a cue name,
  the demo is too vague — clarify with the user.
- Don't propose a zoom for every cue. Most cues stay wide. The hard
  rules in step 5 are baked in to make under-zooming the safe default.
- Don't ask the user to edit `events.json`. If timing is off, re-record
  or fix the proposal.
- Don't skip exploration. Without aria-labels and region knowledge the
  proposal degenerates to "guess the rect".
