"""
apply-zoom-proposal.py — apply zoom regions from a proposal file to the
V1 compound clip in the currently-open Resolve timeline.

USAGE
    Open Resolve, open the project you imported with to-resolve.py.
    Make sure V1 has a single compound clip spanning the take. Then:

        python3 resolve/apply-zoom-proposal.py --run <slug>

    Reads:
        runs/<slug>/zoom-proposal.json
        runs/<slug>/events.json
        runs/<slug>/script.md            (for cue ordering)

PROPOSAL FORMAT
    {
      "viewport": { "width": 1920, "height": 1080 },     # informational
      "regions": [
        {
          "id":          "providers-form",                # display label
          "anchor_cues": ["api-key-input", "test-button"],# ≥1, in script order
          "rect_css":    { "x": 720, "y": 280, "width": 480, "height": 240 },
                                                           # optional. If absent,
                                                           # centre = mean of
                                                           # anchor clicks' bbox
                                                           # centres.
          "zoom":            1.5,                          # peak zoom factor
          "pre_ms":          300,                          # ramp-in ms
          "hold_ms":         400,                          # hold-at-peak ms
          "post_ms":         400,                          # ramp-out ms
          "min_duration_ms": 2000,                         # span threshold;
                                                           # single-cue regions
                                                           # always fail this
                                                           # unless hold ≥ 1500
          "rationale":   "..."                             # optional, ignored
        },
        ...
      ]
    }

CUE → CLICK BINDING
    Cues in `script.md` are matched to clicks in `events.json` by ORDINAL —
    Nth cue in the script binds to the Nth click in the recording. As a
    safety net, each binding is verified by comparing the cue name to
    the click's `label` (case-insensitive substring); mismatches print a
    warning but don't abort.

    If cue count and click count differ, the script aborts and prints
    the misalignment.

REQUIREMENTS
    - Resolve Studio (Free version doesn't expose scripting).
    - A timeline open with V1 carrying a compound clip from to-resolve.py.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
DEFAULT_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

os.environ.setdefault("RESOLVE_SCRIPT_API", DEFAULT_API)
os.environ.setdefault("RESOLVE_SCRIPT_LIB", DEFAULT_LIB)
sys.path.insert(0, os.path.join(os.environ["RESOLVE_SCRIPT_API"], "Modules"))


CUE_RE = re.compile(r"\{\{([a-z0-9_\-]+)\}\}", re.IGNORECASE)


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


def extract_cues(script_md: str) -> list[str]:
    """Return cue names in the order they appear in the script."""
    return [m.group(1).lower() for m in CUE_RE.finditer(script_md)]


def bind_cues_to_clicks(
    cues: list[str], clicks: list[dict],
) -> tuple[dict[str, dict], list[str]]:
    """Ordinal 1:1 bind. Returns (cue_name → click_event, warnings).

    Aborts (raises) if counts differ. Substring label-verification is
    soft — emit a warning and proceed with the ordinal binding.
    """
    if len(cues) != len(clicks):
        raise RuntimeError(
            f"cue/click count mismatch: {len(cues)} cues in script vs "
            f"{len(clicks)} clicks in events.json. Re-record, or "
            f"adjust cues in script.md so they match the take."
        )

    binding: dict[str, dict] = {}
    warnings: list[str] = []
    for cue, ev in zip(cues, clicks):
        binding[cue] = ev
        ev_label = (ev.get("label") or "").lower().strip()
        cue_lc = cue.lower()
        if not ev_label:
            warnings.append(
                f"cue {cue!r}: click has no label — can't verify identity"
            )
            continue
        # Tolerant match: identical, or one is a substring of the other,
        # or any token of one appears in the other (cues often use
        # hyphens; aria-labels often use spaces).
        norm = lambda s: re.sub(r"[\s\-_]+", " ", s).strip()
        cue_norm = norm(cue_lc)
        ev_norm = norm(ev_label)
        if (
            cue_norm == ev_norm
            or cue_norm in ev_norm
            or ev_norm in cue_norm
            or any(tok and tok in ev_norm for tok in cue_norm.split())
        ):
            continue
        warnings.append(
            f"cue {cue!r} (click #{clicks.index(ev) + 1}): "
            f"expected element identifier doesn't match click label "
            f"{ev.get('label')!r}. Wrong element clicked, missed click, "
            f"or stray double-click?"
        )
    return binding, warnings


def build_region_blocks(
    regions: list[dict],
    binding: dict[str, dict],
    *,
    fps: float,
    capture_scale: float,
    frame_w: int,
    frame_h: int,
    add_zooms,
) -> tuple[str, str, list[dict]]:
    """For each region, emit Fusion tool blocks (Size/Displacement/Path/
    Transform) chained off the previous Transform's output. Returns
    (tools_text, last_tool_name, status_per_region).

    Empty tools_text + last_tool="MediaIn1" if every region was skipped.
    """
    blocks: list[str] = []
    prev_source = "MediaIn1"
    status: list[dict] = []
    tool_idx = 0

    for region in regions:
        rid = region.get("id", f"region-{tool_idx + 1}")
        anchor_cues = region.get("anchor_cues", [])
        zoom = float(region.get("zoom", 1.3))
        pre_ms = int(region.get("pre_ms", 300))
        hold_ms = int(region.get("hold_ms", 400))
        post_ms = int(region.get("post_ms", 400))
        min_duration_ms = int(region.get("min_duration_ms", 2000))

        if not anchor_cues:
            status.append({"id": rid, "kept": False,
                           "reason": "no anchor_cues"})
            continue

        # Resolve cues → clicks.
        try:
            anchor_clicks = [binding[c.lower()] for c in anchor_cues]
        except KeyError as e:
            status.append({"id": rid, "kept": False,
                           "reason": f"unknown cue {e.args[0]!r}"})
            continue

        first_click_t = anchor_clicks[0].get("t", 0)
        last_click_t = anchor_clicks[-1].get("t", 0)
        span_ms = last_click_t - first_click_t

        # Hard rules.
        if len(anchor_cues) < 2 and hold_ms < 1500:
            status.append({"id": rid, "kept": False,
                           "reason": "single-cue region needs hold_ms ≥ 1500"})
            continue
        if span_ms < min_duration_ms and len(anchor_cues) >= 2:
            status.append({"id": rid, "kept": False,
                           "reason": f"span {span_ms} ms < min_duration_ms {min_duration_ms}"})
            continue

        # Resolve centre.
        rect = region.get("rect_css")
        if rect:
            cx_css = rect["x"] + rect["width"] / 2
            cy_css = rect["y"] + rect["height"] / 2
        else:
            sum_x = sum_y = 0.0
            for ev in anchor_clicks:
                bbox = ev.get("bbox") or {
                    "x": ev.get("x", 0), "y": ev.get("y", 0),
                    "width": 0, "height": 0,
                }
                sum_x += bbox["x"] + bbox["width"] / 2
                sum_y += bbox["y"] + bbox["height"] / 2
            n = len(anchor_clicks)
            cx_css = sum_x / n
            cy_css = sum_y / n

        cx_frame = cx_css * capture_scale
        cy_frame = cy_css * capture_scale
        cx_norm_raw = cx_frame / frame_w
        # Fusion's Y is bottom-up (0 = bottom), CSS is top-down.
        cy_norm_raw = 1.0 - (cy_frame / frame_h)
        cx_norm, cy_norm = add_zooms.frame_fill_clamp(cx_norm_raw, cy_norm_raw, zoom)

        pre_frames = add_zooms.ms_to_frames(pre_ms, fps)
        hold_frames = add_zooms.ms_to_frames(hold_ms, fps)
        post_frames = add_zooms.ms_to_frames(post_ms, fps)

        click_frame_first = add_zooms.ms_to_frames(first_click_t, fps)
        click_frame_last = add_zooms.ms_to_frames(last_click_t, fps)
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
            "anchor_cues": anchor_cues,
            "span_s": span_ms / 1000,
            "centre_norm": (cx_norm, cy_norm),
            "zoom": zoom,
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
    proposal_path = run_dir / "zoom-proposal.json"
    events_path = run_dir / "events.json"
    script_path = run_dir / "script.md"

    for p in (proposal_path, events_path, script_path):
        if not p.exists():
            print(f"FAIL: {p} not found", file=sys.stderr)
            return 2

    proposal = json.loads(proposal_path.read_text())
    events = json.loads(events_path.read_text())
    script_md = script_path.read_text(encoding="utf-8")

    cues = extract_cues(script_md)
    clicks = [e for e in events.get("events", []) if e.get("kind") == "click"]
    print(f"cues in script: {len(cues)}")
    print(f"clicks in events.json: {len(clicks)}")

    try:
        binding, warnings = bind_cues_to_clicks(cues, clicks)
    except RuntimeError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 3
    if warnings:
        print("\nbinding warnings:")
        for w in warnings:
            print(f"  ! {w}")

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
    if len(v1_items) > 1:
        print(f"WARN: V1 has {len(v1_items)} clips — using the first one. "
              "Did you forget to merge into a compound?")
    clip = v1_items[0]
    print(f"\ntarget clip: {clip.GetName()}")
    print(f"timeline fps: {fps}")
    print(f"frame size:  {frame_w}×{frame_h}")

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

    regions = proposal.get("regions", [])
    if not regions:
        print("proposal has no regions — nothing to apply.")
        return 0

    extra_tools, last_tool, statuses = build_region_blocks(
        regions, binding,
        fps=fps,
        capture_scale=capture_scale,
        frame_w=frame_w, frame_h=frame_h,
        add_zooms=add_zooms,
    )
    print("\nregions:")
    for r, s in zip(regions, statuses):
        rid = s.get("id", "?")
        if s["kept"]:
            cx, cy = s["centre_norm"]
            cues_label = ", ".join(s["anchor_cues"])
            rationale = (r.get("rationale") or "").strip()
            tail = f" — {rationale}" if rationale else ""
            print(f"  ZOOM  {rid}: zoom={s['zoom']:.2f}× span={s['span_s']:.1f}s "
                  f"centre=({cx:.2f},{cy:.2f}) cues=[{cues_label}]{tail}")
        else:
            print(f"  skip  {rid}: {s['reason']}")

    if not extra_tools.strip():
        print("\nno regions kept — patched comp would be a no-op. "
              "Adjust the proposal or accept this take as wide-shot only.")
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
