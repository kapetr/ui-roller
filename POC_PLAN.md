# POC Plan — speech + click effects + Resolve zoom

## Goal

End-to-end Meet DAM video produced by:

1. Scripted Playwright capture of the DAM UI (or hand-driven for chat
   segment if deterministic capture proves too constraining).
2. Composited cursor + click ring/ripple over the raw screencast.
3. TTS narration generated separately (already in `speech-generation/`).
4. Zoom/pan + final timeline polish in DaVinci Resolve.

ffmpeg owns the deterministic layer compositing (cursor, click effects).
Resolve owns cinematic transforms (zoom, pan) and the final mux.

## Pipeline (target)

```
recorder        →  raw.mov
                   cursor.mov            (transparent ProRes 4444)
                   click.mov             (transparent ProRes 4444)
                   events.json
                   actual.timings.json   (per-cue drift)

TTS (separate)  →  narration.mp3
                   speech.timings.json   (cues → audio at_ms)

resolve/to-resolve.py
                →  Resolve project file
                   - V1 raw, V2 cursor, V3 click overlays
                   - A1 narration
                   - Marker per click event (named with label/cue)
                   - Transform keyframes per click (1.0× → 1.6× zoom,
                     anchored on bbox)
                   → hand off for final polish + render
```

## Steps

### 1. Click-effect compositor — TODO
Mirror the cursor compositor in `src/compositor/click-effects.ts`. Per
click event, render an expanding ring centred on `bbox` (fall back to
`(x,y)`) — ~500ms life, fade out. Stream RGBA to ffmpeg, output
transparent ProRes 4444 → `out/click.mov`. Tunables in config: ring
colour, stroke width, peak radius, ease.

Useful side-benefit: a click ring on the exact frame the click event
fired is the visible test that the alignment fix is correct. Click
landing on the cursor's frame ⇒ alignment good.

### 2. ~~Suppress page hover~~ — SKIPPED
Keeping page hover. Affordance signal matters; some hover-paint lag on
busy beats is acceptable. Documented in `NOTES.md`.

### 3. Resolve export `resolve/to-resolve.py` — TODO
DaVinci Resolve Python scripting API. Smallest possible test first
(connect, print project name) to flush out API quirks. Then:

- Open project (Resolve must be running).
- Create new timeline at the recording's resolution.
- Import `raw.mov`, `cursor.mov`, `click.mov`, narration.
- Place on V1/V2/V3 + A1 starting at 00:00:00:00.
- For each click event: timeline marker named `label` or `cue`.
- For each click event: Transform keyframes on V1 (Zoom + Anchor) —
  1.0× → 1.6× peak around the click time, anchor on bbox centre,
  ease curves matching `easeZoom` (we'll start with the same iOS-style
  cubic-bezier).
- Save project, hand off for polish.

Risks: Resolve's Python API is documented but finicky; needs the
right Python interpreter; some operations are async without obvious
completion signal. Plan extra time.

### 4. Port Meet DAM scene — TODO
`src/scenes/meet-dam.ts` consuming `speech-generation/meet_dam.timings.json`.

- Login, provider walk, connections walk, settings — scripted with
  `cue:` per action.
- Chat segment — ideally configure DAM dev-mode to return a canned/
  scripted response so timing is deterministic. Falls back to step 5
  if the canned approach hits a wall.

End-to-end run, then iterate Resolve easing until it feels right.

### 5. Hand-driven fallback `pnpm record-manual <scene>` — TODO if needed
Non-headless browser; user clicks through the UI naturally. Playwright
tracks every action via page binding (`page.exposeBinding`):

- `mousemove` (sampled at ~30 Hz to keep payload small)
- `click` (full event, with target element bbox)
- `keydown` (for type events; reconstructed into `type` events)

Times are recorded as the user actually performs them — no scripted
timing assumptions. Same `events.json` schema as scripted runs, so the
compositor and Resolve export are unchanged. Speech timings can be
reconciled against the actual play timeline (cues drift to wherever
the user clicked).

This is the path for chat-heavy beats that aren't worth scripting.

## Progress

- [x] v0 scaffold (capture pipeline, ProRes intermediate)
- [x] Cursor compositor (sprite, eased path, curved bezier)
- [x] HD layout @ 2× DPR capture (`--force-device-scale-factor=2`)
- [x] Cursor / page-mouse sync via delay-then-teleport
- [x] Logger / video clock alignment (`Screencast.firstFrame` → `Logger.alignTo`)
- [x] Speech cue plumbing (`actions.click(target, { cue })`, `actual.timings.json`)
- [x] Semantic `waitFor({ visible | text | networkIdle | predicate })`
- [ ] **Click-effect compositor** ← next
- [ ] Resolve export
- [ ] Meet DAM scene
- [ ] Hand-driven fallback (if Meet DAM needs it)

## Open questions

- DAM dev-mode canned chat response — does DAM expose a way to get a
  deterministic response stream for demo purposes? If not, hand-driven
  fallback becomes mandatory rather than optional.
- Resolve target version: confirm Python scripting API matches the
  installed Resolve. Free vs Studio may differ for Fusion macros.
- Audio assembly strategy when chat segment is hand-driven: split
  narration into pre-chat / post-chat tracks and pad silence to absorb
  the variable chat duration. (Today's `actual.timings.json` already
  emits the drift the audio assembler needs.)
