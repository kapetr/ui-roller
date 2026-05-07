# Fusion macros — recorder intro/outro

Reusable Edit-page **transitions** that mirror the intro/outro phases
the `apply-zoom-plan.py` script produces. Built so you can keep
trimming the start and end of a clip without re-running the applier.

## Files

- `intro-slide-zoom-in.setting` — clip slides in from off-screen-right
  (Center.x 1.5 → 0.5, ease-out) over 36 frames; size grows 0.7 → 1.0
  (ease-out) over 18 frames, with a 9-frame overlap. Total: 45 frames
  (1.5 s @ 30 fps).
- `outro-zoom-slide-out.setting` — mirror. Size shrinks 1.0 → 0.7
  (ease-in) over 18 frames, then slide-out to off-left (Center.x 0.5 →
  -1.0, ease-in) over 36 frames, 9-frame overlap. Total: 45 frames.

Both expose the standard `MainInput1` (outgoing) / `MainInput2`
(incoming) → `MainOutput1` shape, with a Transform + Merge inside,
which is how Resolve expects an Edit-page transition macro.

## Install

Copy into Resolve's user **Transitions** folder. macOS:

```sh
DEST="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Templates/Edit/Transitions/Recorder"
mkdir -p "$DEST"
cp resolve/macros/intro-slide-zoom-in.setting "$DEST/"
cp resolve/macros/outro-zoom-slide-out.setting "$DEST/"
```

After Resolve's next restart they show up in **Effects > Toolbox >
Video Transitions > Recorder** (or under Templates depending on your
Resolve version).

> **Don't put them in Effects/.** As Effects, both macros would always
> play from the clip's IN point, which is wrong for the outro. As
> Transitions, Resolve places them based on where you drop them on
> the clip's edges.

## Use

In the Edit page:

1. Trim your clip's start/end to where you want the take to begin/end.
2. **Intro** — drag `intro-slide-zoom-in` onto the **left edge** of the
   clip. It snaps as an incoming transition, plays over the first
   45 frames.
3. **Outro** — drag `outro-zoom-slide-out` onto the **right edge** of
   the clip. It snaps as an outgoing transition, plays over the last
   45 frames.

If you need a different duration than 1.5 s: select the transition,
open the Inspector, change the Duration. The macro's keyframes are at
fixed frame numbers (0..45), so a longer transition holds the final
keyframe value past frame 45; a shorter one truncates. For best
results keep duration ≥ 45 frames.

## Why these exist

`apply-zoom-plan.py` bakes intro/outro into the V2 (or V1 if outer-
layered) compound's Fusion comp at fixed timeline frames. That's fine
for the first apply, but if you re-trim later the keyframes don't
move with the clip's new IN/OUT. These macros sidestep the issue:
they're pinned to the clip's edges by Resolve's transition timing
model, so trimming Just Works.

The script's intro/outro stays — it's still the fastest way to get a
preview going. Swap in the macros for the final cut.
