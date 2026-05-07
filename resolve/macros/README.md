# Fusion macros — recorder intro/outro

Reusable Fusion macros that mirror the intro/outro phases the
`apply-zoom-plan.py` script produces. Built so you can keep trimming
the start and end of a clip without re-running the applier.

## Files

- `intro-slide-zoom-in.setting` — clip slides in from off-screen-right
  (Center.x 1.5 → 0.5, ease-out) over 36 frames; size grows 0.7 → 1.0
  (ease-out) over 18 frames, with a 9-frame overlap. Total: 45 frames
  (1.5 s @ 30 fps).
- `outro-zoom-slide-out.setting` — mirror. Size shrinks 1.0 → 0.7
  (ease-in) over 18 frames, then slide-out to off-left (Center.x 0.5 →
  -1.0, ease-in) over 36 frames, 9-frame overlap. Total: 45 frames.

Both expose `MainInput1` (the clip) → `MainOutput1`. No external
parameters.

## Install

Copy into Resolve's user Fusion templates folder. macOS:

```sh
DEST="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Templates/Edit/Effects/Recorder"
mkdir -p "$DEST"
cp resolve/macros/intro-slide-zoom-in.setting "$DEST/"
cp resolve/macros/outro-zoom-slide-out.setting "$DEST/"
```

After Resolve's next restart they show up in **Effects > Templates >
Effects > Recorder**.

To install as Edit-page **transitions** (snap to clip edges), put
them under `…/Templates/Edit/Transitions/Recorder/` instead. The
macros declare a single input/output; they work as effects but Resolve
may treat them as crossfade transitions when placed in the Transitions
folder. Test which behaviour fits your workflow.

## Use

In the Edit page:
1. Trim your clip's start/end to where you want the take to begin/end.
2. Drag `intro-slide-zoom-in` onto the start of the clip; the macro's
   45 frames play over the head.
3. Drag `outro-zoom-slide-out` onto the end; same idea, last 45 frames.

If you need a different duration than 1.5 s, open the Fusion page on
the clip and drag the keyframes on the Spline editor — the relative
shape stays the same.

## Why these exist

The `apply-zoom-plan.py` script bakes intro/outro into the V2 (or V1
if outer-layered) compound's Fusion comp at fixed timeline frames.
That's fine for the first apply, but if you re-trim later the
keyframes don't move with the clip's new IN/OUT. These macros
sidestep the issue: they're pinned to the clip's edges by Resolve's
transition/effect timing model, so trimming Just Works.

The script's intro/outro stays — it's still the fastest way to get a
preview going. Swap in the macros for the final cut.
