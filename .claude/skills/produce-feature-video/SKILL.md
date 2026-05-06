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

The zoom logic in `add-zooms.py` is opinionated. Read this before
tweaking the parameters:

### When zoom IN

- A user is **doing something local** — filling a form, reading a panel,
  clicking through a small set of related buttons.
- The "thing" is **smaller than ~30% of the viewport width**. Bigger
  than that and the zoom is annoying — the eye already sees it.
- The **camera stays put** during the activity. If multiple clicks
  happen in the same neighbourhood, ONE zoom holds across all of them.

### When zoom OUT

- The **whole page is changing** — navigation, route change,
  big content swap. Zooming during a transition makes the viewer dizzy.
- The cursor is **moving across the screen** to a new area. Zoom out,
  travel, zoom in fresh.
- The narration is **describing the layout overall** ("the get-started
  bar, the sidebar, the main pane"). Wide shots beat tight shots.

### When NOT to zoom at all

- The **whole UI fits in the frame and matters as a whole**. A get-started
  bar walk where the bar IS the layout — keep it wide.
- **Title screens, hero shots, outros**. These belong at 1.0×.
- The user is **passively watching** (agent thinking, file streaming).
  No zoom; just hold the wide shot.

### Knobs

`add-zooms.py` defaults: peak zoom 1.6×, ramp-in 300 ms, hold 400 ms,
ramp-out 400 ms. Tune with `--zoom`, `--pre-ms`, `--hold-ms`,
`--post-ms`. **Don't push past 1.8×** — anything tighter on a 4K
recording starts to look pixely.

## Recovery / iteration

| Problem | Fix |
|---|---|
| Recorder hangs after browser close | Cmd+W in the browser; SIGINT (Ctrl+C) in the terminal also works |
| Voice sounds wrong on a phrase | Reword the phrase; TTS pacing depends on punctuation |
| Click landed off-target | Re-record the take. Don't try to edit the events.json. |
| Zoom feels too aggressive | `--zoom 1.4 --pre-ms 500` for softer pulses |
| Two clicks should have been one zoom | They probably were spatially distant; merge them in Resolve manually after `add-zooms.py` runs |
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
