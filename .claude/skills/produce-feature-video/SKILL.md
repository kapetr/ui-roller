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

## Operating convention

You **run** every CLI command yourself via Bash — `pnpm tts`,
`pnpm record-manual`, `pnpm assemble`, `python3 resolve/...`. Don't
hand the user a command to copy-paste; you have the run-folder
context, so you issue it with the right `--run <slug>` slug.

What you **ask** the user to do is the parts only a human can: provide
the brief, confirm the script, drive the browser during a recording,
do the GUI steps in Resolve, polish the final cut. When you're about
to launch a long-running interactive command (notably the recorder),
brief them on what'll happen, wait for "ready", then run it.

When a command exits, decide:

- **Looks good** → continue to the next step, with a one-line update
  ("take captured, 6 clicks, going to composite").
- **Looks off** (click count mismatch, error, missing output) → tell
  the user what you see and ask whether to re-run or proceed.

Don't proceed silently when something's off; don't ask permission at
every step when it's clearly working.

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
init.json            # optional: per-run state setup (localStorage, etc.)
script.md            # narration with {{cue}} markers
zoom-intent.md       # narrative pre-recording intent (step 5)
speech.mp3           # TTS output (or user-supplied)
speech.txt           # cleaned text for premium-voice hand-off
raw.mov              # screencast (after recording)
cursor.mov           # cursor track (after compositing)
click.mov            # click-ring track (after compositing)
events.json          # click + move + navigate events with timing
zoom-plan.json       # concrete plan derived from intent + events (step 10)
final.mp4            # quick-reference composite preview
```

## Tools you'll invoke

- `pnpm tts --run <slug>` — TTS narration mp3 from the script
- `pnpm record-manual <url> --run <slug>` — opens browser; user clicks
  through to narration; logs `events.json` + `raw.mov`
- `pnpm assemble --run <slug>` — composites cursor + click rings
- `python3 resolve/to-resolve.py --run <slug>` — Resolve timeline assembly
- `python3 resolve/apply-zoom-plan.py --run <slug>` — dumb pipe:
  reads `zoom-plan.json` + `events.json`, emits Fusion keyframes
- `python3 resolve/add-zooms.py --run <slug>` — heuristic fallback that
  groups clicks by cluster. Kept for cases where the agent isn't
  available to author a plan; not the default

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
  data, a particular page, theme preference, dismissed onboarding,
  feature flags).

If the source code is local, read it too — it's often faster than
clicking around to learn the UI.

Write a tight `runs/<slug>/exploration.md`: route → action → element
identifier → region note. One paragraph or table per scene the demo
covers.

If Playwright isn't available (sandboxed env, auth wall, app not
running), tell the user explicitly and ask for screenshots + a list of
clickable elements with their aria-labels. Don't guess.

#### Init config (per-run state)

Apps often need particular initial state to record cleanly: light/dark
theme, dismissed onboarding modals, a feature flag. Capture localStorage
needs in `runs/<slug>/init.json`:

```json
{
  "localStorage": {
    "theme": "light",
    "tour-dismissed": "true"
  }
}
```

The recorder applies these to the start URL's origin via Playwright's
`addInitScript` before the page loads, so the app sees them during
its first render. Cross-origin navigations (e.g. to a Keycloak login)
are not affected.

**Apply the same state during your Playwright exploration** so the
UI you map matches what the recording will capture — set the same
localStorage entries via `browser_evaluate` after each navigation,
or pass them through with the same init script if your MCP supports
it. If you skip this, your bboxes might be from the dark theme and
the recording from the light theme, and the proposal will look
correct but render off.

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
- A leading Markdown title (`# Script — …`) is fine for file
  organisation; `pnpm tts` strips Markdown headers before sending to
  the API. **But** if you hand off to the ElevenLabs UI for a premium
  voice, paste `speech.txt` (auto-generated, cleaned), not
  `script.md` — the UI doesn't strip anything.

Iterate with the user. Don't move on until they confirm the script.

### 4. Annotate cues

Re-write `script.md` with `{{cue-name}}` markers — **one per click
the user will actually make**. Don't add cues for visible-but-not-clicked
moments (e.g. a tab that's already active won't get clicked, so it gets
no cue). Don't add cues for keyboard-only beats (Tab between fields,
Enter to submit). The cue→click binder is in-script-order; if you add
a cue with no corresponding click, the binder leaves it unbound and
any region anchored on it is skipped.

The binder is also tolerant of *extra* clicks the user makes (stray
clicks into inputs, accidental icon hits) — it scans forward from the
last matched click for each cue. So you don't need to micromanage the
recording; just make sure the cued clicks happen in script order.

**Use the actual `aria-label` or `id` from your exploration as the cue
name** when one exists. Lowercase, hyphens or underscores. The binder
matches cue → click via tolerant token comparison against each click's
`label`, so cue `set-up-a-provider` matches a click whose label is
`"Set up a provider"`.

```
First, open the {{providers-tab}}. Paste your key into the
{{api-key-input}} and click {{test-button}}. {{success-banner}}
```

If a target has no useful label (icon button without aria-label, etc.),
invent a descriptive cue (`{{primary-cta}}`) and note in
`exploration.md` what it points to.

The TTS strips `{{cues}}` automatically; you don't need a separate
"cue-stripped" file.

### 5. Write zoom intent (pre-recording)

Write `runs/<slug>/zoom-intent.md` — plain English, narrative. Where
the camera should focus and why; where it should stay wide. No JSON,
no anchor names, no schema. The point is to align with the user on
the *visual story* before the take, while reasoning is cheap.

Two sections, brief:

- **Wide** — beats that should stay zoomed out (page navigations,
  layout-overview narration, opening/closing wide shots).
- **Zoom-in** — for each, one paragraph: which beat, what region of
  the UI, rough zoom factor (1.3–1.5 is the safe band), and a
  sentence on why.

Validate with the user. The hard zoom rules below still inform what
you propose, but enforcement happens later.

**Hard rules to honour when proposing zoom regions** — these belong wide:

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

**Validate the intent with the user before moving on.** Don't just
write the file silently — summarise each region you're proposing in
one or two lines, and any region you considered but deliberately
*didn't* include because of the hard rules. Ask the user to confirm
or redirect. The intent doc is your written contract with them; the
concrete plan in step 10 will be derived from it.

### 6. Generate audio

Try the canonical TTS first:

```sh
ELEVENLABS_API_KEY=… pnpm tts --run <slug> [--speed 1.1]
```

Default voice is Brian (free tier); default speed is 1.1 (a touch
faster than neutral, which reads slow for product walkthroughs). For
a different free-tier voice, pass the voice id as the second arg. For
slower/faster delivery, pass `--speed` (clamped to ElevenLabs' 0.7–1.2
envelope).

`--run` mode also writes `runs/<slug>/speech.txt` — the cleaned text
sent to TTS, with `{{cues}}`, Markdown headers, and orphan spaces
before punctuation already stripped. **Use this for premium-voice
hand-off** (see below); never paste `script.md` into a TTS UI directly,
because TTS will read both the title and the cue tokens aloud.

If the user wants a premium ElevenLabs voice (Library/shared voices
require a paid plan; the API can't access them on free tier), tell
them: *"Premium voices need the ElevenLabs UI. Paste the contents of
`runs/<slug>/speech.txt` (already cleaned), generate, and save the
result as `runs/<slug>/speech.mp3`. Tell me when you're done."*

Listen-check before recording. If any sentence sounds wrong, reword
in `script.md` and regenerate — TTS prosody depends on punctuation,
not just words.

### 7. Record the take

**You** run the command yourself with Bash. The user clicks through
the browser the recorder opens — that's their part. Don't make them
copy a CLI invocation; you've got the run-folder context, you can
issue it with the right `--run` slug.

Before launching: tell the user the per-take checklist (see below).
Wait for them to confirm "ready". Then run:

```sh
pnpm record-manual <start-url> --run <slug>
```

(With `--run`, the recorder picks up `runs/<slug>/speech.mp3`
automatically if it exists.)

Per-take checklist for the user:

- Put on headphones — the audio plays through the system, not into the
  recording.
- Make sure the app is in the demo's starting state (logged in/out as
  needed, fixtures seeded, on the right page). Cite the specific state
  from `exploration.md` so they can match it.
- 5-second prep window from the first frame, then audio starts.
- Click decisively, paced to the narration. Pause briefly before clicks
  the narration emphasises ("…click {{test-button}}, *[pause]* green
  check").
- Hold for ~1 s after the last click, then close the browser window
  (Cmd+W or red ✕). Recording finalises automatically.
- If the take is fluffed, close the browser early — takes are cheap.

Use a generous `timeout` (the command runs as long as the user takes
to click through plus encoding time — figure on 5 min). The recorder
prints `events.json` size and click count when it finishes; eyeball
those before moving on.

After the recorder exits, inspect `events.json` and report each click's
`t` and `label` to the user (it's a quick `node -e` one-liner; do it
even when things look right — the user wants to see what happened).
Then:

- All cued clicks present in script order → continue to step 8
  automatically; tell the user something like "take is in, 6 clicks,
  going to composite".
- A cue's click is missing (e.g. user tabbed instead of clicked) →
  drop the cue from the script if the click was never going to happen
  for stylistic reasons, or re-record. Ask the user.
- The recorder errored → surface the error, offer to re-run.
- Extra clicks (user fumbled a bit) → fine, the binder skips them.
  Mention them in the report so the user knows you saw them, but
  don't re-record on their account.

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
> Compound Clip. Tell me when done — both the applier and add-zooms.py
> need a single compound on V1."*

### 10. Resolve part 2 — resolve intent into a concrete plan, apply

This is **your** step. Don't run the applier yet.

Read everything you need to make concrete decisions:

- `runs/<slug>/zoom-intent.md` — what we agreed before recording.
- `runs/<slug>/script.md` — narration + cue markers.
- `runs/<slug>/events.json` — the actual recording. For each click,
  inspect `t` (ms), `label`, `bbox`. Note `kind: "navigate"` events
  too — they mark page transitions where the camera should be wide.
- `runs/<slug>/speech.mp3` (or its duration) and the audio offset
  from `events.json`.audio.startedAtMs — to reason about where in
  the audio each click landed.

Map intent to recording:

- For each intent region, find which clicks it should bind to. Use
  click `label` as a hint (matches the cue you used in the script
  most of the time), but trust `t` and `bbox` more — they don't lie.
- Stray clicks the user made by accident: ignore them.
- Cued clicks that didn't happen (user tabbed or used keyboard): if
  the region needs that anchor, fall back to a `*_t_ms` time anchor
  picked from where in the audio the beat lives.
- Time-only regions (no surrounding click) need an explicit `rect_css`
  to tell the camera where to look.

Write `runs/<slug>/zoom-plan.json`. Schema:

```json
{
  "regions": [
    {
      "id": "login-form",
      "first_click_index": 0,    // 0-indexed into events.json clicks
      "last_click_index": 1,
      "first_t_ms": null,         // overrides click_index when present
      "last_t_ms": null,
      "rect_css": null,           // optional; mean of click bboxes otherwise
      "zoom": 1.5,
      "pre_ms": 300, "hold_ms": 400, "post_ms": 400,
      "rationale": "..."
    }
  ]
}
```

`pre_ms`/`hold_ms`/`post_ms` semantics are unchanged (ramp-in /
trailing dwell after last anchor / ramp-out). The dominant zoom
duration is still `last_t - first_t` plus ramps; `min_duration_ms`
isn't a field anymore — you choose the anchors so the camera dwells
long enough.

**Show the plan to the user**: print each region in plain English
("login-form: clicks 0 and 1, zoom 1.5×, pre 300 / hold 400 / post
400, centred on the form"), plus any clicks you deliberately ignored
as strays. Confirm before applying.

Once confirmed, run:

```sh
python3 resolve/apply-zoom-plan.py --run <slug>
```

This is a dumb pipe — reads `zoom-plan.json` + `events.json`, emits
a Fusion comp with Transform/Size keyframes, attaches it to V1.

After the comp lands:

- Scrub the timeline. Each region should pulse zoom around its
  anchor times.
- The user can delete individual Transforms in Fusion to remove a
  zoom they don't like, or hand-edit Size keyframes for one specific
  region.

If a region needs revision, edit `zoom-plan.json` directly and re-run
the applier with `--clear`. You don't need to redo the whole flow.

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
| Click landed off-target                  | Re-record. The plan can stray-click-skip but not relabel a click   |
| Zoom feels too aggressive                | Lower the region's `zoom` in `zoom-plan.json`; raise `pre_ms`/`post_ms` for softer ramps      |
| Camera misses a beat you wanted          | Add or extend a region in `zoom-plan.json` — use `first_t_ms` to anchor on a non-click moment |
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
- Don't add a cue for every click reflexively. Cues mark beats you'll
  reference later (in `zoom-intent.md` or while reasoning). If a cue
  has no purpose, drop it.
- Don't propose a zoom for every cue. Most cues stay wide. The hard
  rules in step 5 are there to make under-zooming the safe default.
- Don't ask the user to edit `events.json`. If timing is off, re-record
  or fix `zoom-plan.json`.
- Don't skip step 10's "show the plan" beat. Confirming click-by-click
  with the user is what catches the case where you bound a stray
  click to a region.
- Don't skip exploration. Without aria-labels and region knowledge the
  intent degenerates to "guess the rect".
