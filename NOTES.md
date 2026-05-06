# Notes — known issues, design rationale, deferred work

## Cursor / hover sync

### Solved (commit `<this one>`): 600+ ms logger-vs-video offset
Logger's t=0 used to be at construction time, but the video's t=0 is the
first screencast frame — which only arrives after browser launch + first
navigate + first paint. That gap (~300–700 ms) shifted every event in
events.json forward of its visual content by exactly that amount, so the
compositor drew the cursor lagging real visuals by that much. Fixed by
re-zeroing the logger to the wall clock of the first screencast frame
(see `Logger.alignTo` + `Screencast.firstFrame`).

### Still off: post-click hover repaint latency on busy pages
After the alignment fix, the static Keycloak login is frame-perfect. The
post-login DAM pills still show a residual lag of up to ~2 s between the
cursor's logged click frame and when the hover/active visual becomes
visible in the screencast — but only on busy pages.

Why: at click event time we call `page.mouse.move(x, y, {steps:20})` then
`page.mouse.click(x, y)`. CDP delivers those mouse events to the browser,
which then runs the page's hover/active style + paint pipeline. On the
post-login DAM page (lots of state transitions in flight) those repaints
queue behind unrelated rendering work — sometimes 300 ms, sometimes 2 s.
CDP screencast only emits a new frame when the page visually changes, so
the first frame showing the hover state can be a long way after the
click event timestamp. There's no real fix that doesn't either:

- Drive the page mouse along the eased path (lockstep) — we tried this;
  cursor crawls at 3 s/segment because mouse events serialise behind
  hover repaints.
- Suppress page hover styling entirely (one CSS injection — plausibly
  the right call for product demos; the cursor + composited click
  effects do all the affordance signalling).

For click effects (rings/ripples added later), the click *event*
timestamp lines up with the cursor's arrival frame, so the effect will
land on the cursor's frame regardless of when the page's own hover/
active visual catches up.

## Click-effect timing on busy pages
The click ring is rendered at `event.effectT` if present, else `event.t`.
`effectT` is set in `Actions.click` to the wall time of the next screencast
frame after `mouse.click` — i.e., the first moment the page repaints in
response to the click. On the static Keycloak login this lands within
200 ms (button :active state); on busy DAM transitions it lands 1–1.7 s
later, usually right when the destination page paints.

It's a heuristic. The next emitted frame can sometimes be a tiny
intermediate paint (a button hover dropping, a scrollbar redraw)
rather than the destination's first paint. When that happens the ring
fires earlier than the viewer perceives the click. Sturdier signals
worth adding if it bites in real use:

- Detect URL change post-click (catches navigation clicks reliably).
- MutationObserver scoped to the main content area (catches state
  changes that aren't full navigations).
- Wait for screencast frame rate to fall idle (page has settled).

For now we accept the heuristic — it's strictly better than tying the
ring to click dispatch and the POC isn't gated on perfect sync here.

## Manual-drive mode (deferred)

A second recorder mode where the user drives a non-headless browser by
hand and the script logs every mousemove + click via `page.exposeBinding`.
Same `events.json` schema. Trades reproducibility for naturally curved,
hover-synced motion. Probably worth building when scripted scenes start
costing more than they save (chat-heavy beats are the canonical case).
