---
name: produce-feature-video
description: End-to-end workflow for producing a short product feature
  video using this repo's tools — narration script, TTS audio, hand-driven
  Playwright recording, cursor + click compositing, smart zoom-ins via
  DaVinci Resolve, final edit. Use when the user wants to record a new
  walkthrough video of a UI feature.
---

# Producing a feature video

This skill turns a written script into a polished feature video in roughly
**1 hour of human time** plus a few minutes of recorder/compositor wall-clock.
Every routine step (cursor sprite, click rings, zoom keyframes) is
automated; you keep the creative bits — script, recording pace, final
trim, intro/outro.

## Required tools (already in repo)

- `pnpm tts <script>` — generates narration mp3 from a script
- `pnpm record-manual <url> --audio <mp3>` — opens browser; you click
  through paced to the audio; logs `events.json` + raw screencast
- `pnpm assemble <label>` — composites cursor + click rings into
  layered ProRes tracks
- `python3 resolve/to-resolve.py <label> --audio <mp3>` — builds a
  Resolve timeline with V1 (raw), V2 (cursor), V3 (click), A1 (audio)
  + click markers
- `python3 resolve/add-zooms.py` — adds zoom-region keyframes on the V1
  compound clip via Fusion
- DaVinci Resolve **Studio** — final cut, audio sync, intro/outro,
  render. (Free version doesn't expose Fusion scripting.)

## Five steps

### 1. Write the script

Plain text in `speech-generation/<name>_script.txt`. Tips:

- Write for the ear, not the page. Read aloud as you write.
- Keep sentences short. Long clauses sound great in your head and
  garbled in TTS.
- Each visual moment ("now the agents page", "click providers") should
  be ONE breath. The recorder will pace clicks to the narration.
- Aim for the same number of "beats" (sentence-ends) as you have major
  click moments. Roughly: each click → one short sentence.

You don't need `{{cue}}` markers for the hand-driven flow — you'll
pace clicks to the audio yourself.

### 2. Generate the audio

```bash
pnpm tts speech-generation/<name>_script.txt
```

Default voice is Brian (free-tier ElevenLabs). For a different voice:
`pnpm tts <script> <voice-id>`. Listen to the result before recording —
if a sentence sounds wrong, re-write it; TTS punctuation choices matter.

### 3. Record the take

Have headphones on. Open a clean dev cluster (no agents, no providers
already configured for the get-started bar to render correctly). Then:

```bash
pnpm record-manual http://humr.localhost:4444/ --audio speech-generation/<name>.mp3
```

What happens:
- Browser opens at the configured viewport.
- 5-second prep window from first frame, then the audio starts.
- You click through to the narration — natural pace, real human motion.
- Hold for ~1 s after your last click (don't cut off the final beat),
  then close the browser window. Recording finalises automatically.

Tips for a clean take:
- Click decisively, don't hover unless you mean to demonstrate hover.
- Pause briefly before clicks the narration emphasises ("...click
  Test, [pause] green check").
- If you fluff a section, just close the browser and re-run; takes are
  cheap and the script is the same.

### 4. Composite cursor + click rings

```bash
pnpm assemble <label>
```

`<label>` is just a name for the take ("manual", "v1", "take2") used
for log lines. Outputs `out/{cursor.mov, click.mov, final.mp4}`. The
final.mp4 is a quick reference you can play directly; the .mov tracks
are what Resolve consumes.

### 5. Resolve assembly

```bash
python3 resolve/probe.py                # one-time: confirm scripting works
python3 resolve/to-resolve.py <label> --audio speech-generation/<name>.mp3
python3 resolve/add-zooms.py --clear
```

In Resolve:
- V1 raw + V2 cursor + V3 click should already be merged into a
  **compound clip**. (If they aren't, select all three tracks → right
  click → New Compound Clip. Subsequent runs of `add-zooms.py` need
  this.)
- The compound now has a Fusion comp with Transform + Size keyframes
  per zoom region. Scrub the timeline; you should see the zoom pulses
  on each click cluster.
- A1 has narration at the offset it actually played during recording.
- Markers per click event for orientation.

What's left for you to do by hand:
- **Trim the head and tail** to match the audio start/end.
- **Fix any mismatches** where you over-/undershot the narration.
  Resolve makes this easy — slip-edit the compound clip a few frames.
- **Add intro / outro** — title card, logo, end card. Use Fusion
  templates or a simple Text+ + Background.
- **Color** if needed (usually not — DAM is dark, recording is dark).
- **Export**: Deliver page → H.264 mp4, Studio quality, 30 fps.

## Zoom philosophy

The zoom logic in `add-zooms.py` is opinionated and **hard to overdo
the wrong way**. Less is more. The defaults bake these rules in; read
them so you know which to override and which to leave alone.

### Hard rules baked into add-zooms.py

1. **Single clicks never get a zoom.** One click is a navigation
   moment, not sustained activity. Stay zoomed out so the viewer can
   see the whole page change.
2. **Click clusters with span < 2 s never get a zoom.** Quick
   double-clicks aren't a "region"; the camera barely arrives before
   it has to leave. Override per-run with `--min-duration-ms`.
3. **The Centre is always clamped to keep the source filling the
   output frame.** No black gutter behind the clip, ever. Edge-of-
   screen click clusters (top-bar pills, sidebar) get pulled toward
   the centre by exactly the amount needed to keep the source covering
   the output. The visible result: the clicked area sits at the edge
   of the framed output, not centred — which is what you want.

### Soft rules — intuitions for picking `--zoom`

- **Default 1.3×** — safe for any region with surrounding content
  that changes (top-bar buttons whose click navigates, sidebar items
  whose click loads a new view). The zoom highlights *which* button is
  clicked without cropping the new content that arrives below.
- **Push to 1.5× for tight forms** — login, single-input dialogs,
  modals where the form is the only thing that matters and the
  surrounding chrome is constant.
- **Don't push past 1.8×** — anything tighter on a 4K recording
  starts to look pixely.

### When zoom IN

- A user is **doing something local for at least a few seconds** —
  filling a form, reading a panel, repeatedly clicking nearby buttons
  whose effect is in the same place.
- The "activity" is **smaller than ~30% of the viewport width**.
  Bigger than that and the zoom is redundant — the eye already
  sees it.

### When zoom OUT (= no Transform)

- The **whole page is changing** — navigation, route change,
  big content swap. Zooming during a transition makes the viewer
  dizzy. (`add-zooms.py` won't zoom on single clicks, which catches
  most of these automatically.)
- The cursor is **moving across the screen** to a new area. Zoom out,
  travel, zoom in fresh in the new region.
- The narration is **describing the layout overall** ("the get-started
  bar, the sidebar, the main pane"). Wide shots beat tight shots.
- The user is **passively watching** (agent thinking, file streaming).

### When NOT to zoom at all

- The **whole UI fits in the frame and matters as a whole**. A get-
  started bar walk where the bar IS the layout — keep it wide.
- **Title screens, hero shots, outros**. These belong at 1.0×.

### Manual override

After `add-zooms.py` runs, you can still:

- **Delete a Transform in Fusion** to remove a zoom you don't like.
  The chain works after deletion; you just lose that region's pulse.
- **Edit Size keyframes by hand** in the Fusion page Inspector to
  change the peak, ramp, or hold timing for one specific region.
- **Re-run with `--zoom 1.5`** for the next take if the default 1.3
  is too subtle for your video.

### Knobs

`add-zooms.py` defaults: peak zoom 1.3×, ramp-in 300 ms, hold 400 ms,
ramp-out 400 ms, min-duration 2000 ms. Tune with `--zoom`,
`--pre-ms`, `--hold-ms`, `--post-ms`, `--min-duration-ms`.

## Recovery / iteration

| Problem | Fix |
|---|---|
| Recorder hangs after browser close | Cmd+W in the browser; SIGINT (Ctrl+C) in the terminal also works |
| Voice sounds wrong on a phrase | Reword the phrase; TTS pacing depends on punctuation |
| Click landed off-target | Re-record the take. Don't try to edit the events.json. |
| Zoom feels too aggressive | Lower `--zoom` (default 1.3); push `--pre-ms` / `--post-ms` higher for softer ramps |
| A region got skipped you wanted zoomed | Lower `--min-duration-ms`, or add a beat to the recording so the region spans > 2 s |
| A zoomed region you didn't want | Delete the corresponding `Transform_iSize` / `Transform_iPath` / `Transform_i` triple in the Fusion graph |
| Black gutter showing behind the clip | Shouldn't happen — the script clamps the Centre. If it does, the patched comp has a stale Centre value; re-run with `--clear` |
| Two clicks should have been one zoom | They were spatially distant; either merge them by widening `--group-threshold` (TODO param) or hand-edit in Resolve |
| Resolve `add-zooms.py` produces black | The Fusion comp has a known fragile area around keyframes; run `--basic` to verify the simple path works, then re-run default |
| Need a different language | Re-run `pnpm tts` with the translated script + matching voice; `events.json` is unchanged so the rest of the pipeline reuses the same take |

## What this skill is NOT

- Not a substitute for tools like Clueso/Tella when you want a no-code
  GUI workflow.
- Not zero-shot — you still need to choose the script, drive the
  browser, and polish in Resolve.
- Not for live demos. The output is recorded video.

## File layout

```
speech-generation/
  <name>_script.txt        narration text
  <name>.mp3               TTS output
out/
  raw.mov                  screencast (ProRes)
  cursor.mov               composited cursor (transparent ProRes 4444)
  click.mov                composited click rings (transparent ProRes 4444)
  events.json              click + move events with timing
  final.mp4                quick-reference composited preview
.claude/skills/produce-feature-video/SKILL.md   this file
NOTES.md                   technical notes / known issues
POC_PLAN.md                roadmap + progress checklist
```
