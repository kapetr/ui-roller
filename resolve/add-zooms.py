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
    --static        diagnostic — apply a single static zoom around the
                    first click only, no keyframes
    --clear         delete any existing Fusion comp on the V1 clip
                    before importing (use to start fresh after a failed
                    earlier run)

WHY COMP-FILE IMPORT
    The Fusion-Python API for setting keyframes (SetInput with a time
    argument; comp.AutoKey + CurrentTime + SetInput; tool.Param[time] =
    value) all silently fail to promote a parameter to animated under
    the Resolve we tested. The reliable path is to generate a Fusion
    composition (.comp) text file with BezierSpline keyframes pre-baked
    in the Lua-table format Fusion saves natively, then attach it to
    the clip with TimelineItem.ImportFusionComp(path) — a documented
    stable API.

    Side effect: the V1 clip gains a new Fusion composition. To edit
    the zoom curves by hand later, double-click the clip and switch to
    the Fusion page.

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
import tempfile
from pathlib import Path

DEFAULT_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
DEFAULT_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

os.environ.setdefault("RESOLVE_SCRIPT_API", DEFAULT_API)
os.environ.setdefault("RESOLVE_SCRIPT_LIB", DEFAULT_LIB)
sys.path.insert(0, os.path.join(os.environ["RESOLVE_SCRIPT_API"], "Modules"))


def ms_to_frames(ms: float, fps: float) -> int:
    return int(round(ms / 1000.0 * fps))


def fmt_keyframe_size(frame: int, value: float) -> str:
    return (
        f"            [{frame}] = {{ {value:.4f}, "
        f"RH = {{ 1, 0 }}, LH = {{ -1, 0 }}, "
        f"Flags = {{ Linear = true, LockedY = true }} }},"
    )


def fmt_keyframe_path(frame: int, t_progress: float, x: float, y: float) -> str:
    """XYPath keyframe format. The leading number is the path's normalized
    time progress (0..1 across the whole path)."""
    return (
        f"            [{frame}] = {{ {t_progress:.6f}, "
        f"X = {x:.4f}, Y = {y:.4f}, "
        f"RX = 0.0, RY = 0.0, LX = 0.0, LY = 0.0, "
        f"Flags = {{ Linear = true, LinearAcceleration = true }} }},"
    )


def patch_comp_text(
    base_text: str,
    extra_tools: str,
) -> str:
    """Insert extra_tools (Tool definitions) just before the closing brace
    of the Tools = { ... } block in base_text, and re-route the Saver
    (MediaOut1) to read from Transform1 instead of MediaIn1.

    Resolve's exported comps use:
      - `Tools = { ... }`  (no `ordered()` wrapper)
      - `MediaIn1 = Loader { ... }` with a CustomData.MediaProps block
        carrying the source linkage we MUST preserve verbatim.
      - `MediaOut1 = Saver { Inputs = { Input = Input { SourceOp = "MediaIn1", ... } } }`

    Patching strategy:
      1. Find `Tools = {`, walk braces to its match, insert our tools
         just before that close brace.
      2. Inside the resulting MediaOut1 = Saver { ... } block, replace
         `SourceOp = "MediaIn1"` with `SourceOp = "Transform1"`.
    """
    import re

    m = re.search(r"Tools\s*=\s*\{", base_text)
    if not m:
        raise RuntimeError("couldn't find 'Tools = {' block in exported comp")
    open_idx = m.end() - 1  # position of the '{'

    # Walk forward counting braces to find the matching close.
    depth = 0
    i = open_idx
    in_string = False
    string_ch = ""
    while i < len(base_text):
        ch = base_text[i]
        if in_string:
            if ch == string_ch and base_text[i - 1] != "\\":
                in_string = False
        elif ch in '"\'':
            in_string = True
            string_ch = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    close_idx = i
    if close_idx >= len(base_text):
        raise RuntimeError("couldn't find end of Tools block")

    # Resolve's exporter doesn't put a trailing comma after the last tool;
    # add one before our additions.
    head = base_text[:close_idx].rstrip()
    sep = "," if not head.endswith(",") else ""
    patched = head + sep + "\n" + extra_tools + "\n\t\t" + base_text[close_idx:]

    # Re-route the Saver (MediaOut1) to consume Transform1's output. Match
    # the Saver-block SourceOp specifically so we don't disturb the Loader's
    # `MediaIn1 = Loader` self-name elsewhere.
    patched, n_replacements = re.subn(
        r"(MediaOut1\s*=\s*Saver\s*\{[\s\S]*?SourceOp\s*=\s*\")MediaIn1(\")",
        r"\1Transform1\2",
        patched,
        count=1,
    )
    if n_replacements != 1:
        raise RuntimeError("couldn't find MediaOut1's Saver SourceOp to re-route")
    return patched


def build_extra_tools(
    click_events: list[dict],
    *,
    fps: float,
    capture_scale: float,
    frame_w: int,
    frame_h: int,
    zoom: float,
    pre_ms: int,
    hold_ms: int,
    post_ms: int,
) -> str:
    """Build a Fusion .comp file text with MediaIn → Transform (animated
    Size + Center via BezierSpline + XYPath) → MediaOut.
    """
    pre_frames = ms_to_frames(pre_ms, fps)
    hold_frames = ms_to_frames(hold_ms, fps)
    post_frames = ms_to_frames(post_ms, fps)

    # (frame, value) for Size; (frame, x, y) for Center.
    size_kf: list[tuple[int, float]] = [(0, 1.0)]
    center_kf: list[tuple[int, float, float]] = [(0, 0.5, 0.5)]
    last_frame = 0

    for ev in click_events:
        click_frame = ms_to_frames(ev.get("t", 0), fps)
        f_pre = max(0, click_frame - pre_frames)
        f_peak_in = click_frame
        f_peak_out = click_frame + hold_frames
        f_post = f_peak_out + post_frames

        bbox = ev.get("bbox") or {
            "x": ev.get("x", 0), "y": ev.get("y", 0), "width": 0, "height": 0,
        }
        bbox_cx = (bbox["x"] + bbox["width"] / 2) * capture_scale
        bbox_cy = (bbox["y"] + bbox["height"] / 2) * capture_scale
        cx_norm = bbox_cx / frame_w
        # Fusion's Y is bottom-up; screencast Y is top-down.
        cy_norm = 1.0 - (bbox_cy / frame_h)

        size_kf += [
            (f_pre, 1.0),
            (f_peak_in, zoom),
            (f_peak_out, zoom),
            (f_post, 1.0),
        ]
        center_kf += [
            (f_pre, 0.5, 0.5),
            (f_peak_in, cx_norm, cy_norm),
            (f_peak_out, cx_norm, cy_norm),
            (f_post, 0.5, 0.5),
        ]
        last_frame = max(last_frame, f_post)

    # Path progress is 0..1 evenly across keyframes.
    n_path = max(1, len(center_kf) - 1)
    path_lines = "\n".join(
        fmt_keyframe_path(f, i / n_path, x, y)
        for i, (f, x, y) in enumerate(center_kf)
    )
    size_lines = "\n".join(fmt_keyframe_size(f, v) for f, v in size_kf)
    end_frame = last_frame + 30

    # Returns just the new tools (SizeAnim, CenterAnim, Transform1) as
    # comp-file text, ready to be patched into the auto-generated comp.
    return f"""        SizeAnim = BezierSpline {{
            SplineColor = {{ Red = 252, Green = 102, Blue = 153 }},
            CtrlWZoom = false,
            NameSet = true,
            KeyFrames = {{
{size_lines}
            }},
        }},
        CenterAnim = XYPath {{
            DrawMode = "ModifyOnly",
            CtrlWZoom = false,
            NameSet = true,
            KeyFrames = {{
{path_lines}
            }},
        }},
        Transform1 = Transform {{
            CtrlWZoom = false,
            Inputs = {{
                Center = Input {{ SourceOp = "CenterAnim", Source = "Position" }},
                Size = Input {{ SourceOp = "SizeAnim", Source = "Value" }},
                Input = Input {{ SourceOp = "MediaIn1", Source = "Output" }},
            }},
            ViewInfo = OperatorInfo {{ Pos = {{ 220, 0 }} }},
        }},"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="out")
    parser.add_argument("--zoom", type=float, default=1.6, help="peak zoom factor")
    parser.add_argument("--pre-ms", type=int, default=300, help="ramp-in duration before click (ms)")
    parser.add_argument("--hold-ms", type=int, default=400, help="hold-at-peak duration after click (ms)")
    parser.add_argument("--post-ms", type=int, default=400, help="ramp-out duration (ms)")
    parser.add_argument("--clear", action="store_true",
                        help="delete any existing Fusion comp on V1 first")
    parser.add_argument("--static", action="store_true",
                        help="DIAGNOSTIC: static zoom anchored on first click, no keyframes")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    events_path = out_dir / "events.json"
    if not events_path.exists():
        print(f"FAIL: {events_path} not found", file=sys.stderr)
        return 2
    events = json.loads(events_path.read_text())

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
    v1_items = timeline.GetItemListInTrack("video", 1)
    if not v1_items:
        print("FAIL: V1 is empty", file=sys.stderr)
        return 6
    if len(v1_items) > 1:
        print(f"WARN: V1 has {len(v1_items)} clips — using the first one. "
              "Did you forget to merge into a compound?")
    clip = v1_items[0]
    print(f"target clip:    {clip.GetName()}")
    print(f"timeline fps:   {fps}")
    print(f"frame size:     {frame_w}×{frame_h}")

    # Clear existing Fusion comps first. DeleteFusionCompByName has been
    # observed returning False even when the delete succeeded; just log
    # and move on rather than treating False as fatal.
    if args.clear or clip.GetFusionCompCount() > 0:
        for name in list(clip.GetFusionCompNameList()):
            ok = clip.DeleteFusionCompByName(name)
            print(f"  deleted Fusion comp: {name} → {ok}")
        remaining = clip.GetFusionCompCount()
        if remaining > 0:
            print(f"  WARN: {remaining} comp(s) remain after delete — "
                  f"will export the latest one anyway")

    click_events = [e for e in events.get("events", []) if e.get("kind") == "click"]

    # Step 1: let Resolve create a default Fusion comp on the clip. This
    # auto-links MediaIn1 to the clip's source (the magic that breaks
    # when we import a from-scratch comp).
    print("\nadding default Fusion comp (Resolve auto-links MediaIn1 to source)…")
    if clip.AddFusionComp() is None:
        print("FAIL: AddFusionComp returned None", file=sys.stderr)
        return 7

    # Step 2: export the comp we just added — it's the highest index.
    # Even if a stale comp survived the clear pass, the newest one is
    # the one Resolve auto-linked to the source.
    base_idx = clip.GetFusionCompCount()
    base_path = str(out_dir / "_fusion_base.comp")
    print(f"  comp count: {base_idx}, names: {clip.GetFusionCompNameList()}")
    if not clip.ExportFusionComp(base_path, base_idx):
        print(f"FAIL: ExportFusionComp(\"{base_path}\", {base_idx}) returned False",
              file=sys.stderr)
        return 8
    # Fusion's exported comps are UTF-8, not the platform default.
    base_text = Path(base_path).read_text(encoding="utf-8")
    print(f"  exported base comp ({len(base_text)} chars) → {base_path}")

    # Step 3: build extra tools (or static fallback) and patch into base.
    if args.static:
        if not click_events:
            print("FAIL: --static needs at least one click event", file=sys.stderr)
            return 9
        ev = click_events[0]
        bbox = ev.get("bbox") or {"x": ev["x"], "y": ev["y"], "width": 0, "height": 0}
        bbox_cx = (bbox["x"] + bbox["width"] / 2) * capture_scale
        bbox_cy = (bbox["y"] + bbox["height"] / 2) * capture_scale
        cx = bbox_cx / frame_w
        cy = 1.0 - (bbox_cy / frame_h)
        extra_tools = f"""        Transform1 = Transform {{
            Inputs = {{
                Center = Input {{ Value = {{ {cx:.4f}, {cy:.4f} }} }},
                Size = Input {{ Value = {args.zoom:.4f} }},
                Input = Input {{ SourceOp = "MediaIn1", Source = "Output" }},
            }},
            ViewInfo = OperatorInfo {{ Pos = {{ 220, 0 }} }},
        }},"""
    else:
        if not click_events:
            print("no click events to keyframe — done.")
            return 0
        extra_tools = build_extra_tools(
            click_events,
            fps=fps,
            capture_scale=capture_scale,
            frame_w=frame_w,
            frame_h=frame_h,
            zoom=float(args.zoom),
            pre_ms=args.pre_ms,
            hold_ms=args.hold_ms,
            post_ms=args.post_ms,
        )

    patched = patch_comp_text(base_text, extra_tools)
    patched_path = str(out_dir / "_fusion_patched.comp")
    Path(patched_path).write_text(patched, encoding="utf-8")
    print(f"  patched comp ({len(patched)} chars) → {patched_path}")
    print(f"  clicks: {len(click_events)} keyframed")

    # Step 4: clear all comps (best effort) and import the patched one.
    for name in list(clip.GetFusionCompNameList()):
        clip.DeleteFusionCompByName(name)

    new_comp = clip.ImportFusionComp(patched_path)
    if new_comp is None:
        print(f"\nFAIL: ImportFusionComp returned None.")
        print(f"      Inspect {patched_path} — Fusion couldn't parse it.")
        return 10

    # Make sure the freshly-imported comp is the active one (Resolve may
    # leave a stale earlier comp loaded if delete didn't fully clear).
    final_names = clip.GetFusionCompNameList()
    if final_names:
        clip.LoadFusionCompByName(final_names[-1])
    print(f"  final comps on V1: {final_names}")

    print(f"\n✓ imported as Fusion comp on V1 clip")
    if not args.static:
        print(f"  Size:   1.0 → {args.zoom} → 1.0 around each click")
        print(f"  Center: animates to bbox centre, returns to (0.5, 0.5)")
    print("\nIn Resolve: switch to the Fusion page, click Transform1, you")
    print("should see Size + Center as animated curves with keyframes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
