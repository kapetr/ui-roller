"""
add-zooms.py — apply per-click zoom-in pulses to the V1 compound clip
in the currently-open Resolve timeline.

USAGE
    Open Resolve, open the project you imported with to-resolve.py.
    Make sure V1 has a single compound clip spanning the take. Then:

        python3 resolve/add-zooms.py

OPTIONS
    --out-dir       recorder output dir (default: out)
    --zoom          peak zoom factor (default: 1.6)
    --pre-ms        zoom-in ramp duration before the click (default: 300)
    --hold-ms      hold at peak after click (default: 400)
    --post-ms       zoom-out ramp duration (default: 400)

WHY FUSION
    Resolve's edit-page Inspector keyframes aren't exposed via the
    scripting API in any reliable way — TimelineItem.SetProperty only
    sets static values. The only documented + working approach for
    keyframed transform animation is a Fusion composition on the clip:
    insert a Transform tool, set Size + Center keyframes via the
    `tool.Input[frame] = value` syntax. That's what this does.

    Side effect: the clip on V1 gains a Fusion composition. To edit
    the zoom curves by hand later, double-click the clip and switch
    to the Fusion page.

REQUIREMENTS
    - Resolve Studio (Free version doesn't expose scripting).
    - A timeline open with at least one clip on V1 (ideally the
      compound clip created by to-resolve.py).
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
DEFAULT_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

os.environ.setdefault("RESOLVE_SCRIPT_API", DEFAULT_API)
os.environ.setdefault("RESOLVE_SCRIPT_LIB", DEFAULT_LIB)
sys.path.insert(0, os.path.join(os.environ["RESOLVE_SCRIPT_API"], "Modules"))


def ms_to_frames(ms: float, fps: float) -> int:
    return int(round(ms / 1000.0 * fps))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="out")
    parser.add_argument("--zoom", type=float, default=1.6, help="peak zoom factor")
    parser.add_argument("--pre-ms", type=int, default=300, help="ramp-in duration before click (ms)")
    parser.add_argument("--hold-ms", type=int, default=400, help="hold-at-peak duration after click (ms)")
    parser.add_argument("--post-ms", type=int, default=400, help="ramp-out duration (ms)")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="if the V1 clip already has a Fusion comp, delete it first "
             "(otherwise we error out instead of clobbering custom work)",
    )
    parser.add_argument(
        "--static",
        action="store_true",
        help="DIAGNOSTIC: apply a single static zoom around the first "
             "click's bbox, no keyframes. Use this to verify the Fusion "
             "wiring works at all before worrying about per-click pulses.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    events_path = out_dir / "events.json"
    if not events_path.exists():
        print(f"FAIL: {events_path} not found", file=sys.stderr)
        return 2

    with events_path.open() as f:
        events = json.load(f)

    capture_scale = events.get("captureScale", 1)
    viewport = events.get("viewport", {"width": 1920, "height": 1080})
    frame_w = viewport["width"] * capture_scale
    frame_h = viewport["height"] * capture_scale

    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except ImportError as e:
        print(f"FAIL: can't import DaVinciResolveScript: {e}", file=sys.stderr)
        return 2

    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        print("FAIL: Resolve not running or scripting disabled", file=sys.stderr)
        return 3

    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None:
        print("FAIL: open a project first", file=sys.stderr)
        return 4

    timeline = project.GetCurrentTimeline()
    if timeline is None:
        print("FAIL: open the timeline you imported with to-resolve.py", file=sys.stderr)
        return 5

    fps = float(project.GetSetting("timelineFrameRate") or "30")
    timeline_start = timeline.GetStartFrame()

    v1_items = timeline.GetItemListInTrack("video", 1)
    if not v1_items:
        print("FAIL: V1 is empty", file=sys.stderr)
        return 6
    if len(v1_items) > 1:
        print(f"WARN: V1 has {len(v1_items)} clips — using the first one. "
              "Did you forget to merge into a compound?")

    clip = v1_items[0]
    clip_start = clip.GetStart()  # absolute timeline frame
    print(f"target clip:    {clip.GetName()}")
    print(f"clip start:     frame {clip_start}")
    print(f"timeline fps:   {fps}")
    print(f"frame size:     {frame_w}×{frame_h}")

    # Ensure / acquire a Fusion composition on the clip.
    n_comps = clip.GetFusionCompCount()
    if n_comps > 0 and not args.clear:
        print(f"\nFAIL: clip already has {n_comps} Fusion composition(s). "
              "Pass --clear to delete it and start fresh.", file=sys.stderr)
        return 7

    if n_comps > 0 and args.clear:
        for i in range(n_comps, 0, -1):
            comp = clip.GetFusionCompByIndex(i)
            name = comp.GetAttrs()["COMPS_Name"] if comp else f"comp{i}"
            ok = clip.DeleteFusionCompByName(name)
            print(f"  deleted Fusion comp: {name} → {ok}")

    # Add a fresh Fusion comp. AddFusionComp returns the comp object.
    comp = clip.AddFusionComp()
    if comp is None:
        print("FAIL: AddFusionComp returned None", file=sys.stderr)
        return 8

    # Default Fusion comp on a clip has MediaIn1 → MediaOut1. We insert
    # a Transform between them.
    media_in = comp.FindTool("MediaIn1")
    media_out = comp.FindTool("MediaOut1")
    if not media_in or not media_out:
        print("FAIL: couldn't find MediaIn1 / MediaOut1 in the new comp",
              file=sys.stderr)
        return 9

    # AddTool(name, x, y) — x/y are flow-graph coords; -1,-1 lets Resolve
    # pick a spot. Returns the new tool.
    xform = comp.AddTool("Transform", -1, -1)
    if not xform:
        print("FAIL: AddTool('Transform') returned None", file=sys.stderr)
        return 10

    # Wire MediaIn → Transform → MediaOut. The reliable Fusion-Python form
    # for connecting + setting params is tool.SetInput(name, source_or_value
    # [, time]). Passing a tool object auto-uses its Output.
    xform.SetInput("Input", media_in)
    media_out.SetInput("Input", xform)
    print(f"  wired: {media_in.Name} → {xform.Name} → {media_out.Name}")

    # Read back to verify connections actually took.
    in_src = xform.GetInput("Input")
    out_src = media_out.GetInput("Input")
    print(f"  xform.Input source: {in_src!r}")
    print(f"  MediaOut.Input source: {out_src!r}")
    if in_src is None or out_src is None:
        print(
            "\nWARN: connections don't look applied. The Transform is in the\n"
            "      flow graph but not wired up — that's why no zoom shows.\n"
            "      Try opening the comp in Fusion and dragging arrows manually,\n"
            "      then re-run with --static to test if zoom values stick."
        )

    # Compute keyframe windows + anchor coords per click.
    pre_frames = ms_to_frames(args.pre_ms, fps)
    hold_frames = ms_to_frames(args.hold_ms, fps)
    post_frames = ms_to_frames(args.post_ms, fps)

    click_events = [e for e in events.get("events", []) if e.get("kind") == "click"]

    if args.static:
        if not click_events:
            print("FAIL: --static needs at least one click event in events.json",
                  file=sys.stderr)
            return 11
        ev = click_events[0]
        bbox = ev.get("bbox") or {"x": ev.get("x", 0), "y": ev.get("y", 0), "width": 0, "height": 0}
        bbox_cx = (bbox["x"] + bbox["width"] / 2) * capture_scale
        bbox_cy = (bbox["y"] + bbox["height"] / 2) * capture_scale
        cx_norm = bbox_cx / frame_w
        cy_norm = 1.0 - (bbox_cy / frame_h)

        print(f"\n--static: applying single zoom anchored on first click")
        print(f"  click label:  {ev.get('label', '<unknown>')}")
        print(f"  bbox center:  ({bbox_cx:.0f}, {bbox_cy:.0f}) source px")
        print(f"  Center input: ({cx_norm:.3f}, {cy_norm:.3f}) Fusion-normalised")
        print(f"  Size input:   {args.zoom}")

        xform.SetInput("Size", float(args.zoom))
        xform.SetInput("Center", [cx_norm, cy_norm])

        # Read back.
        size_now = xform.GetInput("Size")
        center_now = xform.GetInput("Center")
        print(f"\n  read-back:")
        print(f"    Size   = {size_now!r}")
        print(f"    Center = {center_now!r}")
        print(
            "\nIf you see a static zoom in the Resolve viewer, the wiring +\n"
            "static SetInput work. Re-run without --static for the keyframed\n"
            "per-click pulses."
        )
        return 0

    print(f"\napplying zoom keyframes for {len(click_events)} clicks…")

    # Keyframing approach: AutoKey on + comp.CurrentTime + SetInput.
    # The third-arg time form of SetInput doesn't promote a parameter to
    # animated reliably across Resolve versions (we tested — it just sets
    # static). The autokey approach is the documented Fusion idiom: set
    # CurrentTime to a frame, then SetInput; Fusion creates a BezierSpline
    # modifier the first time a value differs from the previous keyframe.
    # Wrap the whole batch so we can leave AutoKey off when we're done.
    prev_autokey = comp.GetAttrs().get("COMPB_AutoKeyOn", False)
    comp.SetAttrs({"COMPB_AutoKeyOn": True})

    def keyframe(time: int, size_val: float, center_val: list) -> None:
        comp.CurrentTime = time
        xform.SetInput("Size", float(size_val))
        xform.SetInput("Center", center_val)

    # Baseline keyframe at frame 0 so subsequent value differences become
    # animation rather than static overwrites.
    keyframe(0, 1.0, [0.5, 0.5])

    success = 0
    try:
        for ev in click_events:
            # event.t is video time (ms). Convert to clip-local frame
            # number (Fusion comp time = clip-relative, frame 0 = clip start).
            click_frame = ms_to_frames(ev.get("t", 0), fps)
            f_pre = max(0, click_frame - pre_frames)
            f_peak_in = click_frame
            f_peak_out = click_frame + hold_frames
            f_post = f_peak_out + post_frames

            bbox = ev.get("bbox") or {"x": ev.get("x", 0), "y": ev.get("y", 0), "width": 0, "height": 0}
            bbox_cx = (bbox["x"] + bbox["width"] / 2) * capture_scale
            bbox_cy = (bbox["y"] + bbox["height"] / 2) * capture_scale
            cx_norm = bbox_cx / frame_w
            # Fusion's Y is bottom-up; screencast Y is top-down. Flip.
            cy_norm = 1.0 - (bbox_cy / frame_h)

            try:
                keyframe(f_pre, 1.0, [0.5, 0.5])
                keyframe(f_peak_in, float(args.zoom), [cx_norm, cy_norm])
                keyframe(f_peak_out, float(args.zoom), [cx_norm, cy_norm])
                keyframe(f_post, 1.0, [0.5, 0.5])
                success += 1
                label = (ev.get("cue") or ev.get("label") or "click")[:36]
                print(f"  ✓ {label:36s}  frame {click_frame:5d}  "
                      f"center→({cx_norm:.3f},{cy_norm:.3f})")
            except Exception as e:
                label = ev.get("label", "click")[:36]
                print(f"  ✗ {label:36s}  frame {click_frame:5d}  ERROR: {e}")
    finally:
        comp.SetAttrs({"COMPB_AutoKeyOn": prev_autokey})

    print(f"\n{success}/{len(click_events)} zoom pulses written.")
    print("Switch to the Fusion page on the V1 clip to inspect / tweak the")
    print("Transform tool's Size and Center curves. Right-click any keyframe")
    print("→ Smooth for nicer ease.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
