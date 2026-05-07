"""
apply-zoom-plan.py — emit Fusion Transform/Size keyframes from a
concrete zoom plan onto the V1 compound clip in the currently-open
Resolve timeline.

This is a dumb pipe. The matching/decision work (which clicks anchor
which regions, where to centre, how aggressive to zoom) is done by
the agent reading script.md + events.json + zoom-intent.md and
writing zoom-plan.json. By the time this script runs, every region
already has explicit anchors and parameters.

USAGE
    python3 resolve/apply-zoom-plan.py --run <slug> [--clear]

    Reads:
        runs/<slug>/zoom-plan.json
        runs/<slug>/events.json   (for click bboxes when rect_css absent)

PLAN FORMAT
    {
      "regions": [
        {
          "id":                "login-form",      # display label
          "first_click_index": 0,                   # 0-indexed into events.json's
          "last_click_index":  1,                   # click events. either or both
                                                    # may be absent — see below.
          "first_t_ms":        null,                # explicit time anchor (ms in
          "last_t_ms":         null,                # logger time). overrides
                                                    # *_click_index when present.
          "rect_css":          null,                # optional. centre the zoom
                                                    # on this rect. else: mean
                                                    # of click bbox centres.
          "zoom":              1.5,                 # peak zoom factor
          "pre_ms":            300,                 # ramp-in duration before
                                                    # first anchor
          "hold_ms":           400,                 # dwell at peak after last
                                                    # anchor
          "post_ms":           400,                 # ramp-out duration
          "rationale":         "..."                # optional
        }
      ]
    }

ANCHOR RULES
    For each region, the applier needs a *first* time and a *last* time
    in logger ms. Resolution order:
      1. first_t_ms if present, else clicks[first_click_index].t.
      2. last_t_ms if present, else clicks[last_click_index].t,
         else first_t_ms (single-anchor / lingering).

    rect_css falls back to the mean of all anchored clicks' bbox
    centres when at least one click_index is given. Time-only regions
    must specify rect_css explicitly.

REQUIREMENTS
    - Resolve Studio (Free version doesn't expose scripting).
    - A timeline open with V1 carrying a compound clip from to-resolve.py.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

DEFAULT_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
DEFAULT_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

os.environ.setdefault("RESOLVE_SCRIPT_API", DEFAULT_API)
os.environ.setdefault("RESOLVE_SCRIPT_LIB", DEFAULT_LIB)
sys.path.insert(0, os.path.join(os.environ["RESOLVE_SCRIPT_API"], "Modules"))


def _load_add_zooms():
    """add-zooms.py has a hyphen so it isn't directly importable. Load it
    via importlib so we can reuse its .comp-patching utilities without
    duplication."""
    here = Path(__file__).parent
    spec = importlib.util.spec_from_file_location("add_zooms", here / "add-zooms.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("can't load add-zooms.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _bbox_centre_css(ev: dict) -> tuple[float, float]:
    bbox = ev.get("bbox") or {
        "x": ev.get("x", 0), "y": ev.get("y", 0), "width": 0, "height": 0,
    }
    return (bbox["x"] + bbox["width"] / 2, bbox["y"] + bbox["height"] / 2)


def resolve_region(
    region: dict, clicks: list[dict],
) -> tuple[float, float, tuple[float, float] | None]:
    """Returns (first_t_ms, last_t_ms, centre_css_or_None). Raises on
    missing/inconsistent anchors so the agent has to fix the plan, not
    paper over it."""
    first_idx = region.get("first_click_index")
    last_idx = region.get("last_click_index")
    first_t = region.get("first_t_ms")
    last_t = region.get("last_t_ms")

    def _click_t(idx: int) -> float:
        if idx < 0 or idx >= len(clicks):
            raise ValueError(
                f"region {region.get('id')!r}: click_index {idx} out of "
                f"range (0..{len(clicks) - 1})"
            )
        return float(clicks[idx].get("t", 0))

    if first_t is None:
        if first_idx is None:
            raise ValueError(
                f"region {region.get('id')!r}: needs first_t_ms or first_click_index"
            )
        first_t = _click_t(first_idx)
    if last_t is None:
        last_t = _click_t(last_idx) if last_idx is not None else first_t

    if last_t < first_t:
        raise ValueError(
            f"region {region.get('id')!r}: last_t_ms {last_t} < first_t_ms {first_t}"
        )

    rect = region.get("rect_css")
    if rect:
        centre_css = (rect["x"] + rect["width"] / 2,
                      rect["y"] + rect["height"] / 2)
    else:
        if first_idx is None:
            return (first_t, last_t, None)  # caller errors if it needs centre
        # Average the explicit anchor click bboxes only — NOT every
        # click in [first_idx, last_idx]. Strays the user made between
        # anchors would otherwise pull the centre off-axis.
        anchor_idxs = [first_idx] if last_idx in (None, first_idx) else [first_idx, last_idx]
        sum_x = sum_y = 0.0
        for i in anchor_idxs:
            cx, cy = _bbox_centre_css(clicks[i])
            sum_x += cx
            sum_y += cy
        n = len(anchor_idxs)
        centre_css = (sum_x / n, sum_y / n)

    return (first_t, last_t, centre_css)


def build_region_blocks(
    regions: list[dict],
    clicks: list[dict],
    *,
    fps: float,
    capture_scale: float,
    frame_w: int,
    frame_h: int,
    add_zooms,
) -> tuple[str, str, list[dict]]:
    blocks: list[str] = []
    prev_source = "MediaIn1"
    status: list[dict] = []
    tool_idx = 0

    for region in regions:
        rid = region.get("id", f"region-{tool_idx + 1}")
        zoom = float(region.get("zoom", 1.3))
        pre_ms = int(region.get("pre_ms", 300))
        hold_ms = int(region.get("hold_ms", 400))
        post_ms = int(region.get("post_ms", 400))

        try:
            first_t, last_t, centre_css = resolve_region(region, clicks)
        except ValueError as e:
            status.append({"id": rid, "kept": False, "reason": str(e)})
            continue
        if centre_css is None:
            status.append({"id": rid, "kept": False,
                           "reason": "time-only region needs rect_css"})
            continue

        cx_css, cy_css = centre_css
        cx_frame = cx_css * capture_scale
        cy_frame = cy_css * capture_scale
        cx_norm_raw = cx_frame / frame_w
        # PolyPath waypoint Y is top-down (Y=0 at top, Y=1 at bottom),
        # consistent with CSS. Empirically: passing a bottom-up Y ends
        # up looking at the wrong vertical half of the page.
        cy_norm_raw = cy_frame / frame_h
        cx_norm, cy_norm = add_zooms.frame_fill_clamp(cx_norm_raw, cy_norm_raw, zoom)

        pre_frames = add_zooms.ms_to_frames(pre_ms, fps)
        hold_frames = add_zooms.ms_to_frames(hold_ms, fps)
        post_frames = add_zooms.ms_to_frames(post_ms, fps)

        click_frame_first = add_zooms.ms_to_frames(first_t, fps)
        click_frame_last = add_zooms.ms_to_frames(last_t, fps)
        f_pre = max(0, click_frame_first - pre_frames)
        f_peak_in = click_frame_first
        f_peak_out = click_frame_last + hold_frames
        f_post = f_peak_out + post_frames

        tool_idx += 1
        tool_name = f"Transform{tool_idx}"
        size_name = f"{tool_name}Size"
        path_name = f"{tool_name}Path"
        disp_name = f"{tool_name}Displacement"
        x_pos = 220 + (tool_idx - 1) * 60

        size_kf_seq: list[tuple[int, float]] = []
        if f_pre > 0:
            size_kf_seq.append((0, 1.0))
        size_kf_seq += [
            (f_pre, 1.0),
            (f_peak_in, zoom),
            (f_peak_out, zoom),
            (f_post, 1.0),
        ]
        size_kf = add_zooms._kf_seq_with_handles(size_kf_seq)

        disp_kf_seq: list[tuple[int, float]] = []
        if f_pre > 0:
            disp_kf_seq.append((0, 0.0))
        disp_kf_seq += [
            (f_pre, 0.0),
            (f_peak_in, 1.0),
            (f_peak_out, 1.0),
            (f_post, 0.0),
        ]
        disp_kf = add_zooms._kf_seq_with_handles(disp_kf_seq)

        dx = cx_norm - 0.5
        dy = cy_norm - 0.5
        rx = dx / 3.0
        ry = dy / 3.0

        size_block = (
            f"\t\t{size_name} = BezierSpline {{\n"
            f"\t\t\tSplineColor = {{ Red = 225, Green = 0, Blue = 225 }},\n"
            f"\t\t\tCtrlWZoom = false,\n"
            f"\t\t\tNameSet = true,\n"
            f"\t\t\tKeyFrames = {{\n{size_kf}\n\t\t\t}}\n"
            f"\t\t}}"
        )
        disp_block = (
            f"\t\t{disp_name} = BezierSpline {{\n"
            f"\t\t\tSplineColor = {{ Red = 255, Green = 0, Blue = 178 }},\n"
            f"\t\t\tCtrlWZoom = false,\n"
            f"\t\t\tNameSet = true,\n"
            f"\t\t\tKeyFrames = {{\n{disp_kf}\n\t\t\t}}\n"
            f"\t\t}}"
        )
        path_block = (
            f"\t\t{path_name} = PolyPath {{\n"
            f"\t\t\tDrawMode = \"InsertAndModify\",\n"
            f"\t\t\tCtrlWZoom = false,\n"
            f"\t\t\tInputs = {{\n"
            f"\t\t\t\tDisplacement = Input {{ SourceOp = \"{disp_name}\", Source = \"Value\", }},\n"
            f"\t\t\t\tPolyLine = Input {{\n"
            f"\t\t\t\t\tValue = Polyline {{\n"
            f"\t\t\t\t\t\tPoints = {{\n"
            f"\t\t\t\t\t\t\t{{ Linear = true, X = 0, Y = 0, RX = {rx:.6f}, RY = {ry:.6f} }},\n"
            f"\t\t\t\t\t\t\t{{ Linear = true, X = {dx:.6f}, Y = {dy:.6f}, LX = {-rx:.6f}, LY = {-ry:.6f} }}\n"
            f"\t\t\t\t\t\t}}\n"
            f"\t\t\t\t\t}}\n"
            f"\t\t\t\t}}\n"
            f"\t\t\t}}\n"
            f"\t\t}}"
        )
        transform_block = (
            f"\t\t{tool_name} = Transform {{\n"
            f"\t\t\tCtrlWZoom = false,\n"
            f"\t\t\tInputs = {{\n"
            f"\t\t\t\tCenter = Input {{ SourceOp = \"{path_name}\", Source = \"Position\", }},\n"
            f"\t\t\t\tSize = Input {{ SourceOp = \"{size_name}\", Source = \"Value\", }},\n"
            f"\t\t\t\tInput = Input {{ SourceOp = \"{prev_source}\", Source = \"Output\", }}\n"
            f"\t\t\t}},\n"
            f"\t\t\tViewInfo = OperatorInfo {{ Pos = {{ {x_pos}, 0 }} }},\n"
            f"\t\t}}"
        )

        blocks.extend([size_block, disp_block, path_block, transform_block])
        prev_source = tool_name
        status.append({
            "id": rid, "kept": True,
            "first_t_s": first_t / 1000, "last_t_s": last_t / 1000,
            "centre_norm": (cx_norm, cy_norm),
            "zoom": zoom,
            "rationale": region.get("rationale", ""),
        })

    return ",\n".join(blocks), prev_source, status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True, help="slug of the run folder under runs/")
    parser.add_argument("--clear", action="store_true",
                        help="delete any existing Fusion comp on the V1 clip first")
    args = parser.parse_args()

    run_dir = (Path("runs") / args.run).resolve()
    plan_path = run_dir / "zoom-plan.json"
    events_path = run_dir / "events.json"

    for p in (plan_path, events_path):
        if not p.exists():
            print(f"FAIL: {p} not found", file=sys.stderr)
            return 2

    plan = json.loads(plan_path.read_text())
    events = json.loads(events_path.read_text())
    clicks = [e for e in events.get("events", []) if e.get("kind") == "click"]

    add_zooms = _load_add_zooms()

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
        print("FAIL: open the timeline imported with to-resolve.py", file=sys.stderr)
        return 5

    fps = float(project.GetSetting("timelineFrameRate") or "30")
    v1_items = timeline.GetItemListInTrack("video", 1)
    if not v1_items:
        print("FAIL: V1 is empty", file=sys.stderr)
        return 6
    if len(v1_items) == 1:
        clip = v1_items[0]
    else:
        # Multiple clips on V1 — the compound clip from to-resolve.py
        # is usually the longest (a few-second intro vs 30–60 s walk-
        # through). Pick the longest; warn so the user can verify.
        ranked = sorted(((it, it.GetDuration()) for it in v1_items),
                        key=lambda p: -p[1])
        clip = ranked[0][0]
        print(f"WARN: V1 has {len(v1_items)} clips. Picking longest:")
        for it, dur in ranked:
            mark = "→" if it is clip else " "
            print(f"  {mark} {it.GetName()!r} ({dur} frames)")
    print(f"target clip: {clip.GetName()}")
    print(f"timeline fps: {fps}")
    print(f"frame size:  {frame_w}×{frame_h}")
    print(f"clicks in events.json: {len(clicks)}")

    if args.clear or clip.GetFusionCompCount() > 0:
        for name in list(clip.GetFusionCompNameList()):
            ok = clip.DeleteFusionCompByName(name)
            print(f"  deleted Fusion comp: {name} → {ok}")

    if clip.AddFusionComp() is None:
        print("FAIL: AddFusionComp returned None", file=sys.stderr)
        return 7

    base_idx = clip.GetFusionCompCount()
    base_path = str(run_dir / "_fusion_base.comp")
    if not clip.ExportFusionComp(base_path, base_idx):
        print(f"FAIL: ExportFusionComp({base_path!r}, {base_idx}) returned False",
              file=sys.stderr)
        return 8
    base_text = Path(base_path).read_text(encoding="utf-8")

    regions = plan.get("regions", [])
    if not regions:
        print("plan has no regions — nothing to apply.")
        return 0

    extra_tools, last_tool, statuses = build_region_blocks(
        regions, clicks,
        fps=fps,
        capture_scale=capture_scale,
        frame_w=frame_w, frame_h=frame_h,
        add_zooms=add_zooms,
    )
    print("\nregions:")
    for s in statuses:
        rid = s.get("id", "?")
        if s["kept"]:
            cx, cy = s["centre_norm"]
            tail = f" — {s['rationale']}" if s.get("rationale") else ""
            print(f"  ZOOM  {rid}: zoom={s['zoom']:.2f}× "
                  f"t=[{s['first_t_s']:.2f}..{s['last_t_s']:.2f}]s "
                  f"centre=({cx:.2f},{cy:.2f}){tail}")
        else:
            print(f"  skip  {rid}: {s['reason']}")

    if not extra_tools.strip():
        print("\nno regions kept — patched comp would be a no-op.")
        return 0

    patched = add_zooms.patch_comp_text(base_text, extra_tools, saver_source=last_tool)
    patched_path = str(run_dir / "_fusion_patched.comp")
    Path(patched_path).write_text(patched, encoding="utf-8")
    print(f"\npatched comp ({len(patched)} chars) → {patched_path}")

    for name in list(clip.GetFusionCompNameList()):
        clip.DeleteFusionCompByName(name)

    new_comp = clip.ImportFusionComp(patched_path)
    if new_comp is None:
        print(f"FAIL: ImportFusionComp returned None. "
              f"Inspect {patched_path}.", file=sys.stderr)
        return 10

    print(f"✓ imported Fusion comp on {clip.GetName()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
