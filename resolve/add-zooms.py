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


def patch_comp_text(
    base_text: str,
    extra_tools: str,
    saver_source: str = "Transform1",
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

    # Re-route the Saver (MediaOut1) to consume the *last* Transform's
    # output (TransformN, where N == number of clicks). Matches the
    # Saver-block SourceOp specifically so we don't disturb the Loader's
    # `MediaIn1 = Loader` self-name elsewhere.
    patched, n_replacements = re.subn(
        r"(MediaOut1\s*=\s*Saver\s*\{[\s\S]*?SourceOp\s*=\s*\")MediaIn1(\")",
        rf"\1{saver_source}\2",
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
    viewport_w: float,
    viewport_h: float,
    min_duration_ms: int = 2000,
) -> tuple[str, str, list[list[dict]], list[list[dict]]]:
    """Wraps _build_extra_tools_impl. Returns
    (tools_text, last_tool_name, all_groups, zoom_groups)."""
    return _build_extra_tools_impl(
        click_events,
        fps=fps,
        capture_scale=capture_scale,
        frame_w=frame_w,
        frame_h=frame_h,
        zoom=zoom,
        pre_ms=pre_ms,
        hold_ms=hold_ms,
        post_ms=post_ms,
        viewport_w=viewport_w,
        viewport_h=viewport_h,
        min_duration_ms=min_duration_ms,
    )


def _euclid(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _bbox_center_css(ev: dict) -> tuple[float, float]:
    """Click event's bbox centre in CSS pixels (the events.json space)."""
    bbox = ev.get("bbox") or {
        "x": ev.get("x", 0), "y": ev.get("y", 0), "width": 0, "height": 0,
    }
    return (bbox["x"] + bbox["width"] / 2, bbox["y"] + bbox["height"] / 2)


def group_clicks(
    click_events: list[dict],
    viewport_w: float,
    threshold_frac: float = 0.30,
) -> list[list[dict]]:
    """Group consecutive clicks whose bbox centres are within
    threshold_frac × viewport_w of each other. CSS pixels (events.json).

    The intent: a tight cluster of clicks (form-fill, set of nearby
    buttons) becomes ONE zoom region. Distant clicks (sidebar nav,
    different page) become separate regions, with the camera zoomed
    out between them. Don't overdo it — ~30% of viewport width is a
    reasonable "same neighbourhood" threshold.
    """
    if not click_events:
        return []
    threshold_px = threshold_frac * viewport_w
    groups: list[list[dict]] = [[click_events[0]]]
    for ev in click_events[1:]:
        prev_centre = _bbox_center_css(groups[-1][-1])
        this_centre = _bbox_center_css(ev)
        if _euclid(prev_centre, this_centre) > threshold_px:
            groups.append([ev])
        else:
            groups[-1].append(ev)
    return groups


def filter_zoom_worthy(
    groups: list[list[dict]],
    min_duration_ms: int = 2000,
) -> list[list[dict]]:
    """Drop groups that don't deserve a zoom:

    - **Single-click groups** — one click is a navigation moment, not
      sustained activity. Stay zoomed out and let the viewer see the
      whole page change.
    - **Short groups** — two clicks 200 ms apart aren't a "region"
      either; the camera barely arrives before it has to leave.

    Returns groups in original order, with the unworthy ones removed.
    """
    kept: list[list[dict]] = []
    for group in groups:
        if len(group) < 2:
            continue
        span = group[-1].get("t", 0) - group[0].get("t", 0)
        if span < min_duration_ms:
            continue
        kept.append(group)
    return kept


def frame_fill_clamp(cx: float, cy: float, size: float) -> tuple[float, float]:
    """Clamp a Centre so the zoomed visible region never extends past
    the source frame. With Size = S, the visible region in source space
    spans (1/S) × (1/S) around the Centre — so Centre.x must lie in
    [0.5/S, 1 - 0.5/S], similarly for y. Anything outside that band
    leaves a black gutter on whichever side fell off-source.
    """
    margin = 0.5 / max(size, 1.0)
    cx_c = max(margin, min(1 - margin, cx))
    cy_c = max(margin, min(1 - margin, cy))
    return cx_c, cy_c


def _kf_with_handles(
    t: int,
    v: float,
    t_prev: int | None = None,
    v_prev: float | None = None,
    t_next: int | None = None,
    v_next: float | None = None,
    smooth: bool = True,
) -> str:
    """Render a BezierSpline keyframe.

    smooth=True (default): flat tangents at every keyframe. The handle
    values match the keyframe's value, so the cubic bezier between
    adjacent keyframes is a classic ease-in-out S-curve. No Linear flag.

    smooth=False: linear interpolation. Handles sit on the line between
    adjacent keyframes, and a Linear flag forces straight-line interp.
    Handles must still be present syntactically.

    LH/RH time positions are at 1/3 distance to neighbours either way —
    Fusion's default placement.
    """
    parts = [f"{v:.4f}"]
    if t_prev is not None and v_prev is not None:
        lh_t = t - (t - t_prev) / 3
        lh_v = v if smooth else v + (v_prev - v) / 3
        parts.append(f"LH = {{ {lh_t:.6f}, {lh_v:.6f} }}")
    if t_next is not None and v_next is not None:
        rh_t = t + (t_next - t) / 3
        rh_v = v if smooth else v + (v_next - v) / 3
        parts.append(f"RH = {{ {rh_t:.6f}, {rh_v:.6f} }}")
    if not smooth:
        parts.append("Flags = { Linear = true }")
    return f"\t\t\t\t[{t}] = {{ {', '.join(parts)} }}"


def _kf_seq_with_handles(
    kf_seq: list[tuple[int, float]],
    smooth: bool = True,
) -> str:
    """Render a list of (frame, value) into BezierSpline KeyFrames text.
    Defaults to smooth (ease-in-out) interpolation."""
    lines: list[str] = []
    for j, (t, v) in enumerate(kf_seq):
        t_prev, v_prev = (kf_seq[j - 1] if j > 0 else (None, None))
        t_next, v_next = (kf_seq[j + 1] if j < len(kf_seq) - 1 else (None, None))
        lines.append(_kf_with_handles(t, v, t_prev, v_prev, t_next, v_next, smooth=smooth))
    return ",\n".join(lines)


def _build_extra_tools_impl(
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
    viewport_w: float,
    viewport_h: float,
    min_duration_ms: int = 2000,
) -> tuple[str, str, list[list[dict]], list[list[dict]]]:
    """One Transform per zoom region (group of consecutive nearby clicks).
    Each Transform has:
      - Centre animated via PolyPath (two waypoints — frame centre at
        (0.5, 0.5) and group centre — driven by a Displacement
        BezierSpline that goes 0 → 1 → 0 in lockstep with Size).
      - Size animated by a BezierSpline modifier 1.0 → zoom → 1.0.

    Why animated Centre: with Size=1.0 a Transform with non-default
    Centre still SHIFTS the image (Fusion treats Centre as the source-
    point that maps to the output centre, not just a zoom anchor). A
    chain of Transforms each with their own static Centre cumulatively
    shifts the image off-screen even between zoom regions. Animating
    Centre back to (0.5, 0.5) when Size=1.0 makes each Transform a
    true no-op outside its window.

    Returns (tools_text, last_tool_name, groups).
    """
    pre_frames = ms_to_frames(pre_ms, fps)
    hold_frames = ms_to_frames(hold_ms, fps)
    post_frames = ms_to_frames(post_ms, fps)

    all_groups = group_clicks(click_events, viewport_w)
    zoom_groups = filter_zoom_worthy(all_groups, min_duration_ms=min_duration_ms)

    blocks: list[str] = []
    prev_source = "MediaIn1"

    for i, group in enumerate(zoom_groups, start=1):
        first_click_t = group[0].get("t", 0)
        last_click_t = group[-1].get("t", 0)
        click_frame_first = ms_to_frames(first_click_t, fps)
        click_frame_last = ms_to_frames(last_click_t, fps)

        f_pre = max(0, click_frame_first - pre_frames)
        f_peak_in = click_frame_first
        f_peak_out = click_frame_last + hold_frames
        f_post = f_peak_out + post_frames

        # Group centre = mean of bbox centres (CSS) → frame px → Fusion 0..1.
        sum_x = sum_y = 0.0
        for ev in group:
            cx, cy = _bbox_center_css(ev)
            sum_x += cx
            sum_y += cy
        n = len(group)
        cx_frame = (sum_x / n) * capture_scale
        cy_frame = (sum_y / n) * capture_scale
        cx_norm_raw = cx_frame / frame_w
        # PolyPath waypoint Y is top-down (Y=0 at top), same as CSS.
        cy_norm_raw = cy_frame / frame_h

        # Frame-fill clamp: keep the zoomed visible region inside the
        # source so we never reveal black behind the clip. Edge-of-screen
        # clicks (top-bar pills, sidebar) get pulled toward the centre
        # by exactly the amount needed to keep the source covering the
        # output frame.
        cx_norm, cy_norm = frame_fill_clamp(cx_norm_raw, cy_norm_raw, zoom)

        # PolyPath waypoint offsets from (0.5, 0.5) — Fusion paths are
        # relative to the path's centre which defaults to frame middle.
        # Linear-bezier handles: 1/3 distance to neighbour.
        dx = cx_norm - 0.5
        dy = cy_norm - 0.5
        rx = dx / 3.0
        ry = dy / 3.0

        tool_name = f"Transform{i}"
        size_name = f"{tool_name}Size"
        path_name = f"{tool_name}Path"
        disp_name = f"{tool_name}Displacement"
        x_pos = 220 + (i - 1) * 60

        # Size keyframes: 1.0 → zoom (peak) → 1.0
        size_kf_seq: list[tuple[int, float]] = []
        if f_pre > 0:
            size_kf_seq.append((0, 1.0))
        size_kf_seq += [
            (f_pre, 1.0),
            (f_peak_in, zoom),
            (f_peak_out, zoom),
            (f_post, 1.0),
        ]
        size_kf = _kf_seq_with_handles(size_kf_seq)

        # Displacement keyframes mirror Size: 0 outside the window, 1
        # at peak. Path point 1 = (0,0) offset = (0.5, 0.5); path point 2
        # = (dx, dy) offset = group centre. So displacement=0 keeps
        # Centre at frame middle, displacement=1 puts it at the group.
        disp_kf_seq: list[tuple[int, float]] = []
        if f_pre > 0:
            disp_kf_seq.append((0, 0.0))
        disp_kf_seq += [
            (f_pre, 0.0),
            (f_peak_in, 1.0),
            (f_peak_out, 1.0),
            (f_post, 0.0),
        ]
        disp_kf = _kf_seq_with_handles(disp_kf_seq)

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

    return ",\n".join(blocks), prev_source, all_groups, zoom_groups


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default=None,
                        help="slug of a per-run folder under runs/. Equivalent to "
                             "--out-dir runs/<slug>/.")
    parser.add_argument("--out-dir", default="out")
    parser.add_argument("--zoom", type=float, default=1.3,
                        help="peak zoom factor (default 1.3 — safe for any region "
                             "with surrounding content. Push to 1.5 for tight forms)")
    parser.add_argument("--pre-ms", type=int, default=300, help="ramp-in duration before first click in region (ms)")
    parser.add_argument("--hold-ms", type=int, default=400, help="hold-at-peak duration after last click in region (ms)")
    parser.add_argument("--post-ms", type=int, default=400, help="ramp-out duration (ms)")
    parser.add_argument("--min-duration-ms", type=int, default=2000,
                        help="region must span at least this many ms across its "
                             "clicks to deserve a zoom (default 2000). Single-click "
                             "regions are always skipped.")
    parser.add_argument("--clear", action="store_true",
                        help="delete any existing Fusion comp on V1 first")
    parser.add_argument("--static", action="store_true",
                        help="DIAGNOSTIC: static zoom anchored on first click, no keyframes")
    parser.add_argument("--basic", action="store_true",
                        help="DIAGNOSTIC: simplest possible animation — one Transform, "
                             "three keyframes (1.0 → 1.6 → 1.0 across the whole clip), "
                             "static centre at frame middle. Format copies exactly what "
                             "Resolve writes when you keyframe a Transform manually.")
    args = parser.parse_args()

    out_dir = (Path("runs") / args.run if args.run else Path(args.out_dir)).resolve()
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
    if args.basic:
        # Simplest possible test: ONE Transform, three Size keyframes
        # spanning the whole clip (1.0 → 1.6 → 1.0), static Centre at
        # (0.5, 0.5). Format matches Resolve's saved comp byte-for-byte
        # — including LH/RH handle coordinates Fusion uses for its
        # 1/3-distance bezier handles even with the Linear flag.
        if not click_events:
            f_end = 1000
        else:
            last_t_ms = max(e.get("t", 0) for e in events.get("events", []))
            f_end = ms_to_frames(last_t_ms, fps)
        f_mid = f_end // 2

        def kf_line(t: int, v: float,
                    t_prev: int | None = None, v_prev: float | None = None,
                    t_next: int | None = None, v_next: float | None = None) -> str:
            parts = [f"{v:.4f}"]
            if t_prev is not None and v_prev is not None:
                lh_t = t - (t - t_prev) / 3
                lh_v = v + (v_prev - v) / 3
                parts.append(f"LH = {{ {lh_t:.6f}, {lh_v:.6f} }}")
            if t_next is not None and v_next is not None:
                rh_t = t + (t_next - t) / 3
                rh_v = v + (v_next - v) / 3
                parts.append(f"RH = {{ {rh_t:.6f}, {rh_v:.6f} }}")
            parts.append("Flags = { Linear = true }")
            return f"\t\t\t\t[{t}] = {{ {', '.join(parts)} }}"

        kf_text = ",\n".join([
            kf_line(0, 1.0, t_next=f_mid, v_next=1.6),
            kf_line(f_mid, 1.6, t_prev=0, v_prev=1.0, t_next=f_end, v_next=1.0),
            kf_line(f_end, 1.0, t_prev=f_mid, v_prev=1.6),
        ])

        extra_tools = (
            "\t\tTransform1Size = BezierSpline {\n"
            "\t\t\tSplineColor = { Red = 225, Green = 0, Blue = 225 },\n"
            "\t\t\tCtrlWZoom = false,\n"
            "\t\t\tNameSet = true,\n"
            "\t\t\tKeyFrames = {\n"
            f"{kf_text}\n"
            "\t\t\t}\n"
            "\t\t},\n"
            "\t\tTransform1 = Transform {\n"
            "\t\t\tCtrlWZoom = false,\n"
            "\t\t\tInputs = {\n"
            "\t\t\t\tCenter = Input { Value = { 0.5, 0.5 }, },\n"
            '\t\t\t\tSize = Input { SourceOp = "Transform1Size", Source = "Value", },\n'
            '\t\t\t\tInput = Input { SourceOp = "MediaIn1", Source = "Output", }\n'
            "\t\t\t},\n"
            "\t\t\tViewInfo = OperatorInfo { Pos = { 220, 0 } },\n"
            "\t\t}"
        )
        last_tool = "Transform1"
        print(f"\n--basic: one Transform, 3 Size keyframes "
              f"[0→1.0, {f_mid}→1.6, {f_end}→1.0]")
    elif args.static:
        if not click_events:
            print("FAIL: --static needs at least one click event", file=sys.stderr)
            return 9
        ev = click_events[0]
        bbox = ev.get("bbox") or {"x": ev["x"], "y": ev["y"], "width": 0, "height": 0}
        bbox_cx = (bbox["x"] + bbox["width"] / 2) * capture_scale
        bbox_cy = (bbox["y"] + bbox["height"] / 2) * capture_scale
        cx = bbox_cx / frame_w
        cy = 1.0 - (bbox_cy / frame_h)
        extra_tools = f"""\t\tTransform1 = Transform {{
\t\t\tInputs = {{
\t\t\t\tCenter = Input {{ Value = {{ {cx:.4f}, {cy:.4f} }}, }},
\t\t\t\tSize = Input {{ Value = {args.zoom:.4f}, }},
\t\t\t\tInput = Input {{ SourceOp = "MediaIn1", Source = "Output" }}
\t\t\t}},
\t\t\tViewInfo = OperatorInfo {{ Pos = {{ 220, 0 }} }},
\t\t}}"""
        last_tool = "Transform1"
    else:
        if not click_events:
            print("no click events to keyframe — done.")
            return 0
        extra_tools, last_tool, all_groups, zoom_groups = build_extra_tools(
            click_events,
            fps=fps,
            capture_scale=capture_scale,
            frame_w=frame_w,
            frame_h=frame_h,
            zoom=float(args.zoom),
            pre_ms=args.pre_ms,
            hold_ms=args.hold_ms,
            post_ms=args.post_ms,
            viewport_w=viewport["width"],
            viewport_h=viewport["height"],
            min_duration_ms=args.min_duration_ms,
        )
        print(f"\ngrouped {len(click_events)} click(s) into {len(all_groups)} region(s); "
              f"{len(zoom_groups)} deserve a zoom:")
        for i, group in enumerate(all_groups, start=1):
            t_first = group[0].get("t", 0) / 1000
            t_last = group[-1].get("t", 0) / 1000
            span_s = t_last - t_first
            sum_x = sum_y = 0.0
            for ev in group:
                cx, cy = _bbox_center_css(ev)
                sum_x += cx
                sum_y += cy
            mean_x = sum_x / len(group)
            mean_y = sum_y / len(group)
            labels = ", ".join((ev.get("label", "?") or "?")[:20] for ev in group)
            kept = "ZOOM " if group in zoom_groups else "skip "
            reason = ""
            if group not in zoom_groups:
                if len(group) < 2:
                    reason = " (single click)"
                elif span_s * 1000 < args.min_duration_ms:
                    reason = f" (span {span_s:.1f}s < {args.min_duration_ms/1000:.0f}s)"
            print(f"  {kept} region {i}: t=[{t_first:.1f}..{t_last:.1f}]s "
                  f"({span_s:.1f}s), mean=({mean_x:.0f},{mean_y:.0f}), "
                  f"{len(group)} click(s){reason}")
            if group in zoom_groups:
                print(f"           clicks: [{labels}]")

    patched = patch_comp_text(base_text, extra_tools, saver_source=last_tool)
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
