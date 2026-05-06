# Manual humr recording — clicking plan

This is the test of the hand-driven recorder. We're producing the same
~20 s walk-through the scripted humr scene does, except *you* drive the
browser.

## How it works

1. I run `pnpm record-manual http://humr.localhost:4444/`
2. A Chromium window opens at the configured viewport (1920×1080).
3. You click through the steps below at a natural pace.
4. When you're done, **close the browser window** (Cmd+W, or click the
   red ✕). Hold for ~1 s after your last click first so the final
   action makes it into the recording cleanly.
5. I run `pnpm assemble` to composite the cursor + click rings.

Every mousemove (sampled at 30 Hz) and every click (with element bbox)
is logged to `out/events.json`. The compositor pipeline downstream is
the same one the scripted recorder uses, so cursor + click effects come
out the same way.

## Tips before you start

- **Move smoothly.** Real human motion is what we want; that's the whole
  point of hand-driven mode.
- **Pause briefly at clicks.** ~1 s between clicks gives the click ring
  time to play in the final video.
- **Don't resize the window during recording.** Coordinates are tied to
  viewport geometry.
- **Don't drag** unless that's part of the demo — drags trigger click
  events on whatever you released over.

## Steps

### 0. Wait for the Sign In page to render
The browser opens straight to humr → redirects to Keycloak. Hold for a
moment so the recording has a clean opening frame.

### 1. Sign in
- Click the **Username or email** field.
- Type `dev` (just type into the keyboard — no menu).
- Click the **Password** field.
- Type `dev`.
- Click **Sign In**.

Wait for the post-login page to render (~1–2 s).

### 2. Get-started bar walk
The agents page shows three pills at the top: *Set up a provider*,
*Set up connections*, *Add your first agent*.

- Click pill **2 — "Set up connections"**. Wait for the page to load.
- Click pill **1 — "Set up a provider"**. Wait.
- Click pill **3 — "Add your first agent"**. Wait.

### 3. Sidebar walk
- Click **Settings** in the bottom-left of the sidebar. Wait for the
  Account view to load.
- Click **Agents** in the sidebar to return to the agents list.

### 4. Stop
Hold for ~1 s after your last click (so the final action lands cleanly
in the recording), then close the browser window — Cmd+W or the red ✕.
The recorder finalizes encoding automatically; you don't need to touch
the terminal.

## Total expected duration: ~20–30 seconds.

## After stopping

I'll run:
```
pnpm assemble manual
```

That produces:
- `out/raw.mov`         — your screencast
- `out/cursor.mov`      — composited cursor track
- `out/click.mov`       — composited click rings
- `out/final.mp4`       — everything composited together (4K, 30 fps)

You'll be able to compare it side-by-side with the scripted humr take
to see how the natural cursor motion reads.
