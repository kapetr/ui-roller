# DAM Video Recorder — Problem Statement & Proposed Solution

This document briefs an agent picking up a new project from scratch. It is self-contained: read it once and you should know what to build, why, and what good looks like.

## Context

Petr is building **DAM** (`dam-agents/dam`) — a Kubernetes platform for running AI coding-agent harnesses (Claude Code, Codex, Gemini CLI, pi.dev) in isolated pods, with credential-injecting proxies, scheduled execution, and Slack channels. As DAM ships features, Petr wants short feature videos (60–120s each) showing the UI in action.

This project is the **video recording toolchain** for those videos. It is a separate codebase from DAM. The DAM repo lives at `~/Dev/ibm/dam` and runs locally at `dam.localhost:4444` (k3s via lima, deployed with `mise run cluster:install`, login `dev` / `dev`).

The first reference video is a 1:30 "Meet DAM" walkthrough. The full draft script is at the end of this document — use it as the concrete scene the toolchain has to drive.

## Problem

Existing AI screen recorders (Clueso, Tella, Screen Studio) automate the parts of product video production that are tedious to do by hand:

- **Auto zoom-in on interactions** — every click and typing event becomes a smooth cinematic zoom centered on the action.
- **Click effects** — animated rings, ripples, or highlights at click points.
- **Speech-driven timing** — the screen recording is sliced and timed against a written script with sync points, so generated TTS lands where it should.
- **Branded templates** — backgrounds, intros, outros applied automatically.

Their limits:

- Editing UX for individual zoom curves is shallow.
- Intro/outro screens are templated and rigid.
- Re-recording when the UI changes means redoing the whole take by hand.
- Localization, theme variants, aspect-ratio variants all require fresh recordings.

DaVinci Resolve solves the polish side (intro/outro templates, color, audio, transitions, branding) but has **no native automation for interaction-driven cinematics**. Building those by hand in Resolve is ~3–5 minutes per zoom — fine for one beat, miserable for a whole 90-second tour.

## Proposed Solution

**Drive the browser with Playwright. Log every interaction. Composite the cinematics from the log, not from the recording.**

Because Playwright generates the events, you know precisely when and where each click happened, what was clicked, and how long the action took. That metadata drives:

- A composited cursor sprite (custom look, perfectly synced).
- Zoom and pan keyframes centered on each click.
- Click-effect overlays at each interaction timestamp.
- Markers in Resolve's timeline (if you go that route).

Net effect: you get Clueso's auto-zoom feel **plus** Resolve-grade polish **plus** the ability to re-render the whole video deterministically when the UI, voiceover, language, or aspect ratio changes.

### Side benefit

The recording script is also an end-to-end test. If the UI breaks, the recording fails. For a pre-1.0 product like DAM that's actively renaming and adding features, this matters more than it sounds.

## Architecture

```
  Playwright script (TypeScript)
     ├─ wraps page.mouse.click / move / keyboard.type
     ├─ logs every interaction to events.json
     └─ outputs raw.webm via BrowserContext.recordVideo

  events.json   [{t, kind, x, y, label, target}, ...]
  raw.webm      clean page video, no system chrome, no real cursor

       ↓ post-processor

  Backend A (FFmpeg path):
    Read events.json + raw.webm
    Generate cursor PNG sequence at logged coords
    Generate click-ripple overlay at click timestamps
    Compute zoom/pan curves with eased keyframes
    Render with ffmpeg -filter_complex → final.mp4

  Backend B (DaVinci Resolve path):
    Read events.json + raw.webm
    Open Resolve via its Python API
    Import raw.webm to a new timeline
    Place markers per event (labeled)
    Set Transform keyframes (zoom + pan + ease) per click
    Drop Fusion-macro click ripples on a video track
    Add VO track (ElevenLabs render of script)
    Hand off to user for polish (intro, color, audio, transitions, render)
```

VO is generated separately from the script via **ElevenLabs** (or alternative TTS) and synced in either backend.

## Recommended v0

**FFmpeg path, end-to-end, against a tiny scene first.**

Why: working video output in one sitting. Validates the feel (easing, cursor look, zoom timing) before committing to either backend. If v0 looks right, layer Backend B (Resolve integration) as v1 — same `events.json`, different output stage.

### v0 acceptance criteria

1. Run `pnpm record meet-dam` against a local DAM instance — produces `out/raw.webm` and `out/events.json`.
2. Run `pnpm assemble meet-dam` — produces `out/final.mp4` with composited cursor, click ripples, and per-click zoom-and-pan, no manual editing.
3. The cursor moves smoothly between events (interpolation in the compositor, not jumps).
4. Each click triggers a 1.0×→1.6× zoom centered on the click coordinates with cubic-bezier easing, holds for the action's duration, eases back.
5. Typing animates per-character (not instant fill).
6. Total runtime from `pnpm record` to playable mp4 is under 60 seconds for a 90-second take.

### v0 non-goals

- Audio generation (provide a placeholder mp3 track).
- Intro/outro animations (worry about it in v1).
- Multi-aspect-ratio output (single 1920×1080 is fine).
- Resolve integration.

## Recommended v1

Backend B: emit a Resolve timeline. Resolve has a documented Python scripting API at `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/`. The script can:

- Open Resolve (`Resolve` global, or via DaVinciResolveScript module).
- Create a new timeline, import `raw.webm`.
- For each event in `events.json`, place a labeled marker.
- For click events, set Transform keyframes on the clip (Zoom + Position + Anchor) with the right easing.
- Drop a Fusion macro for click rings on a video track at each click timestamp.
- Add audio track from `voiceover.mp3` (ElevenLabs output).

Daily loop becomes: edit Playwright script + edit VO script → `pnpm record && pnpm assemble && python3 to-resolve.py` → polish in Resolve from a 90%-ready timeline → render.

## Suggested File Layout

```
dam-recorder/
├── package.json                    # pnpm, TS
├── tsconfig.json
├── README.md
├── src/
│   ├── recorder/
│   │   ├── index.ts                # CLI entry: pnpm record <scene>
│   │   ├── browser.ts              # Playwright BrowserContext setup, recordVideo
│   │   └── logger.ts               # event log writer (events.json)
│   ├── actions/
│   │   ├── index.ts                # public API: click, type, move, hover, wait
│   │   └── instrumented.ts         # wraps Playwright primitives + logs events
│   ├── scenes/
│   │   └── meet-dam.ts             # the first reference scene
│   ├── compositor/
│   │   ├── index.ts                # CLI entry: pnpm assemble <scene>
│   │   ├── cursor.ts               # cursor sprite renderer
│   │   ├── zoom.ts                 # event timeline → zoom/pan keyframes
│   │   ├── clicks.ts               # click ripple overlay
│   │   ├── easing.ts               # ease curves, single source of truth
│   │   └── ffmpeg.ts               # filter_complex builder
│   └── shared/
│       ├── events.ts               # event types (TS)
│       └── config.ts               # tunables: zoom factor, easing, typing speed
├── assets/
│   ├── cursor/                     # cursor sprite (default + variants)
│   └── click-ring/                 # ring PNG sequence
├── resolve/
│   └── to-resolve.py               # Backend B (v1)
└── out/
    ├── raw.webm                    # gitignored
    ├── events.json                 # gitignored
    └── final.mp4                   # gitignored
```

## Key Design Decisions

### Events are the source of truth, not the recording

Cursor is composited from the event log, not captured from the OS. This means the recording can run headless, and the cursor look is fully controllable (size, color, glow, motion smear). It also means the cursor and zoom keyframes are guaranteed in sync because they share the same data source.

### Easing is centralized

A single `easing.ts` exports the curves used for cursor moves, zoom in/out, and click ripple expansion. Default: **cubic-bezier(0.32, 0.72, 0, 1)** — the iOS-style "expensive feel" curve that Clueso and Screen Studio use. Default cubic-out feels amateur; spend tuning time here, it's the single biggest "feel" lever.

### Typing animation is real

`page.fill()` is instant and looks fake. Use `page.type(text, { delay: 40-60 })` with small per-character jitter so it doesn't feel metronomic. For long prompts, jitter range ±20ms is plausible.

### Zoom anchor is the click's bounding box, not just the point

A zoom centered on a single pixel feels nervous. Compute the bounding box of the clicked element (Playwright gives this via `locator.boundingBox()`) and zoom to frame the **element**, not the cursor coordinate. The cursor sits inside the framed region.

### Re-runs are the killer feature

Every output of this toolchain — `raw.webm`, `events.json`, `final.mp4` — is reproducible from the Playwright script + the VO script. UI changed? Re-run. Czech voiceover? Swap the TTS source. Vertical 9:16 for social? Re-render with different params. None of this is possible with traditional screen recorders.

## Tool Stack

| Concern | Tool | Notes |
|---|---|---|
| Browser automation | Playwright (TypeScript) | `recordVideo` for clean WebM, `BrowserContext` for isolation |
| Rendering pipeline | FFmpeg | `filter_complex` for cursor + zoom + ripple compositing |
| Resolve integration | Python via Resolve scripting API | Mac-only (Resolve scripting requirement) |
| TTS | ElevenLabs | Best quality at time of writing; alternatives: OpenAI TTS, Play.ht |
| Optional: alt all-in-one | Descript | If full Resolve integration ends up not worth it |

## Gotchas

**Cursor smear during fast moves.** Real cursors don't tweens linearly between sample points; they show motion blur. Compositing a sharp cursor sprite over Playwright's smooth `page.mouse.move({ steps: N })` looks too clinical. Add a subtle motion blur or trail on segments where speed exceeds a threshold.

**Click events arrive before visual feedback.** A click in Playwright fires before the DOM updates. The zoom should start at the click timestamp, but hold the peak until the visual effect (button pressed, dialog opened) actually renders. Detect this with a screenshot diff or a hardcoded post-click hold (200–400ms is usually right).

**Page videos are fixed FPS.** Playwright's `recordVideo` is 25fps by default. For cinematic feel you may want 60. Set `recordVideo.size` and post-process with FFmpeg's `minterpolate` filter, or use OS-level capture and sync on event timestamps.

**OS-level cursor showing through.** If you run headed, the real OS cursor appears in the WebM in addition to your composited one. Run headless, or use `page.mouse.move` only without manual interaction during the take.

**Resolve API is finicky.** It only works when Resolve is open and the Python interpreter is the one Resolve expects (Mac: `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/`). Documented but not great. Test the smallest possible script first (just connect and print project name) before attempting timeline manipulation.

## Reference Scene: "Meet DAM" (target 1:30)

This is the scene v0 should drive. The full script with timing budgets is below. Start with section [0:30–0:38] (Connections skip) as the smallest end-to-end smoke test — it's a single click + page pan, easy to validate the plumbing before you tackle the full take.

```
[0:00–0:08] Hook
VO: "DAM runs your AI coding agent in its own Kubernetes pod —
     credentials safe, network sandboxed, awake when you're not.
     Ninety-second walkthrough from zero."
Screen: Browser bar shows dam.localhost:4444. App opens — empty
        Agents list with the "Get started" progress bar pinned at
        the top showing three numbered pills.

[0:08–0:14] Setup bar callout
VO: "Three steps. DAM walks you through them."
Screen: Cursor traces across the three pills — Set up a provider ·
        Set up connections · Add your first agent.

[0:14–0:30] Step 1 — Provider
VO: "First, plug in a model provider. Switch to API key, paste, hit
     Test, hit Save. DAM verifies the credential live with Anthropic."
Screen: Click pill 1 → Providers view → click API Key tab → paste key
        → click Test → green check "Credential is valid" → click Save
        → auto-jumps back to agents list with pill 1 now checked.

[0:30–0:38] Step 2 — Connections (skip)
VO: "Step two — connections. OAuth apps, MCP servers, and custom
     secrets all live here. We'll cover these in a later video."
Screen: Click pill 2 → Connections view → quick pan down the page so
        each section is on screen for ~2s → click back to Agents.

[0:38–0:54] Step 3 — Add agent
VO: "Click Add Agent, pick a template — Claude Code, pi.dev, or your
     own — name it, hit Create Agent. DAM provisions a pod and brings
     it up automatically. When the pill flips green, click in."
Screen: Click Add Agent → template picker → enter name → Create Agent
        → row appears with pulsing Starting → cut/time-lapse to
        Running → click row → chat view opens.

[0:54–1:08] First prompt
VO: "Give it real work. We'll ask for a tiny TODO app in three files."
Screen: Type the prompt below → send → thought block streams → Write
        chips fire one after another → "Done — 3 files created."

  Prompt: "Build me a tiny TODO app as three files —
           index.html, styles.css, app.js. Tasks should persist
           in localStorage with a satisfying check animation.
           Keep each file under 50 lines."

[1:08–1:22] Files panel — hero beat
VO: "On the right, the Files tab is the agent's sandbox. Open
     app.js and you've got the running code, inline."
Screen: Click Files → tree shows the three files → click app.js →
        syntax-highlighted JS fills the viewer. Brief switch to
        index.html to show it changing.

[1:22–1:28] The rest of the right panel
VO: "Same panel — MCPs, skills, schedules."
Screen: Three quick beats: MCPs → Skills → Schedules tabs flash by,
        ~2s each.

[1:28–1:30] Outro
VO: "That's the loop. More coming."
Screen: Cut to Agents list with the new agent visible; lower-third
        with playlist link.
```

### Recording prerequisites for this scene

- Local DAM cluster running at `dam.localhost:4444` (`mise run cluster:install` from the DAM repo).
- Logged in as `dev` / `dev`.
- Zero agents and zero providers configured (so the Get-started bar renders). Easiest reset: `mise run cluster:uninstall && mise run cluster:install`.
- Anthropic API key in env or in a fixture file the recorder can read and paste.

## Open Questions

To resolve as you build:

- **Cursor sprite design.** Custom shape vs. native macOS look-alike. Affects feel.
- **Zoom factor curve.** 1.6× peak is a starting guess. Tune against real takes.
- **Click ripple style.** Solid ring expand-and-fade vs. concentric pulse. A/B in v0.
- **Motion blur threshold.** What cursor speed triggers a trail? Probably ~1500px/s.
- **Variable bitrate / FPS.** 60fps everywhere or only during action beats.

## Out of Scope (For Now)

- Multi-camera (e.g. webcam picture-in-picture).
- Live audio capture during recording (VO is generated).
- Real-time preview during recording.
- Cloud rendering (everything is local for now).
- Multiple browser support (Chromium-only is fine; Safari/Firefox testing can wait).

## Getting Started

1. `mkdir ~/Dev/ibm/dam-recorder && cd ~/Dev/ibm/dam-recorder`
2. `pnpm init && pnpm add -D playwright typescript @types/node tsx`
3. `pnpm exec playwright install chromium`
4. Scaffold the directory layout above.
5. Build the smallest possible smoke test: open `dam.localhost:4444`, click one button, log the event, save the WebM. Confirm both files exist before adding cursor compositing.
6. Build the cursor compositor next (cursor sprite + interpolation between event coords). This is the foundation everything else stacks on.
7. Add zoom/pan keyframing.
8. Add click ripple.
9. Hook up FFmpeg `filter_complex` to render the lot.
10. Run against the full "Meet DAM" scene. Iterate easing until it feels right.
11. Generate VO via ElevenLabs from the script. Sync in the assemble step.
12. Then — and only then — tackle Backend B (Resolve).

Good luck, and have fun.
