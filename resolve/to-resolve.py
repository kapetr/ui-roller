"""
to-resolve.py — assemble a recorded scene into a DaVinci Resolve timeline.

USAGE
    1. Open Resolve. Open or create a project.
    2. Run: python3 resolve/to-resolve.py [scene]
       (scene defaults to the most recent run's outputs in out/)
    3. Resolve switches to a new timeline with:
         V1: raw.mov
         V2: cursor.mov   (transparent ProRes 4444)
         V3: click.mov    (transparent ProRes 4444)
         A1: narration.mp3 (if --audio path is given)
       and a labelled marker per click event.

    4. Add zoom/pan keyframes by hand around the click markers — the
       Resolve scripting API doesn't expose timeline-clip transform
       keyframes cleanly, so we don't try to automate this in v0.
       Markers give you the exact frame to anchor zooms on.

ENV
    Resolve scripting must be enabled (Preferences > System > General >
    External scripting using = Local). Resolve must be running with a
    project open.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

DEFAULT_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
DEFAULT_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

os.environ.setdefault("RESOLVE_SCRIPT_API", DEFAULT_API)
os.environ.setdefault("RESOLVE_SCRIPT_LIB", DEFAULT_LIB)
sys.path.insert(0, os.path.join(os.environ["RESOLVE_SCRIPT_API"], "Modules"))


def ms_to_frames(ms: float, fps: float) -> int:
    return int(round(ms / 1000.0 * fps))


def import_media(media_pool, paths: list[Path]) -> list:
    """Import each path. ImportMedia returns a list of MediaPoolItem refs.
    We import one at a time so we can map results back to paths cleanly.
    """
    items = []
    for p in paths:
        if not p.exists():
            print(f"  skip (missing): {p.name}")
            items.append(None)
            continue
        result = media_pool.ImportMedia([str(p)])
        if not result:
            print(f"  FAILED to import: {p}")
            items.append(None)
            continue
        items.append(result[0])
        print(f"  imported: {p.name}")
    return items


def append_to_track(media_pool, mp_item, track_index: int) -> Optional[object]:
    """Append a single clip to a specific video track at the timeline start."""
    if mp_item is None:
        return None
    timeline_items = media_pool.AppendToTimeline(
        [{"mediaPoolItem": mp_item, "trackIndex": track_index}]
    )
    return timeline_items[0] if timeline_items else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene", nargs="?", default=None, help="scene name (informational)")
    parser.add_argument("--out-dir", default="out", help="recorder output directory")
    parser.add_argument("--audio", default=None, help="optional narration audio file")
    parser.add_argument("--timeline-name", default=None, help="timeline name")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    events_path = out_dir / "events.json"
    if not events_path.exists():
        print(f"events.json not found at {events_path}", file=sys.stderr)
        return 2

    with events_path.open() as f:
        events = json.load(f)

    viewport = events.get("viewport", {"width": 1920, "height": 1080})
    capture_scale = events.get("captureScale", 1)
    width = viewport["width"] * capture_scale
    height = viewport["height"] * capture_scale

    raw_path = out_dir / "raw.mov"
    cursor_path = out_dir / "cursor.mov"
    click_path = out_dir / "click.mov"
    audio_path = Path(args.audio).resolve() if args.audio else None

    print("inputs:")
    print(f"  raw:    {raw_path}")
    print(f"  cursor: {cursor_path}")
    print(f"  click:  {click_path}")
    print(f"  audio:  {audio_path or '(none)'}")
    print(f"  resolution: {width}×{height}, fps: 30")

    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except ImportError as e:
        print(f"FAIL: cannot import DaVinciResolveScript: {e}", file=sys.stderr)
        print("Run resolve/probe.py first to validate the env.", file=sys.stderr)
        return 2

    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        print("FAIL: Resolve isn't running or scripting is disabled.", file=sys.stderr)
        return 3

    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if project is None:
        print("FAIL: open or create a project in Resolve first.", file=sys.stderr)
        return 4

    print(f"\nproject: {project.GetName()}")

    # Set project resolution + framerate to match the recording.
    project.SetSetting("timelineResolutionWidth", str(width))
    project.SetSetting("timelineResolutionHeight", str(height))
    project.SetSetting("timelineFrameRate", "30")
    project.SetSetting("videoMonitorFormat", f"HD {width}x{height} 30")

    media_pool = project.GetMediaPool()
    root_folder = media_pool.GetRootFolder()
    media_pool.SetCurrentFolder(root_folder)

    # Import all the media in one place so we can map them to tracks.
    print("\nimporting media…")
    paths_to_import = [raw_path, cursor_path, click_path]
    if audio_path:
        paths_to_import.append(audio_path)
    items = import_media(media_pool, paths_to_import)
    raw_item, cursor_item, click_item = items[0], items[1], items[2]
    audio_item = items[3] if audio_path else None

    if raw_item is None:
        print("FAIL: raw.mov is required", file=sys.stderr)
        return 5

    # Create the timeline. CreateEmptyTimeline returns a Timeline object
    # which we'll populate next.
    scene_label = args.scene or out_dir.name
    timeline_name = args.timeline_name or f"recorder · {scene_label}"
    print(f"\ncreating timeline: {timeline_name}")
    timeline = media_pool.CreateEmptyTimeline(timeline_name)
    if timeline is None:
        print("FAIL: CreateEmptyTimeline returned None", file=sys.stderr)
        return 6
    project.SetCurrentTimeline(timeline)

    # Resolve creates a new timeline with one video and one audio track by
    # default. Add tracks for cursor, click, and (if audio) extra audio.
    timeline.AddTrack("video")  # V2 — cursor
    timeline.AddTrack("video")  # V3 — click
    # AppendToTimeline places clips on the LAST track of each type by default
    # unless trackIndex is specified. Specify explicitly.

    print("placing clips:")
    raw_ti = append_to_track(media_pool, raw_item, 1)
    cursor_ti = append_to_track(media_pool, cursor_item, 2)
    click_ti = append_to_track(media_pool, click_item, 3)
    if audio_item is not None:
        append_to_track(media_pool, audio_item, 1)  # A1

    placed = sum(1 for ti in (raw_ti, cursor_ti, click_ti) if ti is not None)
    print(f"  {placed}/3 video tracks placed")

    # Drop a marker per click event. AddMarker(frameId, color, name, note,
    # duration) — frameId is in frames from the timeline start.
    print("\nadding click markers:")
    timeline_start = timeline.GetStartFrame()
    marker_count = 0
    for ev in events.get("events", []):
        if ev.get("kind") != "click":
            continue
        t_ms = ev.get("t", 0)
        offset = ms_to_frames(t_ms, 30)
        name = ev.get("cue") or ev.get("label") or "click"
        # Coordinates in events.json are in CSS px. Scale them to frame
        # px (= timeline px) so the note tells you where to anchor a
        # zoom directly.
        fx = ev.get("x", 0) * capture_scale
        fy = ev.get("y", 0) * capture_scale
        note_parts = [f"frame: {fx:.0f},{fy:.0f}"]
        if ev.get("effectT") is not None:
            note_parts.append(f"response @ {ev['effectT']/1000:.2f}s")
        if ev.get("bbox"):
            bb = ev["bbox"]
            note_parts.append(
                f"bbox: {bb['x']*capture_scale:.0f},{bb['y']*capture_scale:.0f} "
                f"{bb['width']*capture_scale:.0f}×{bb['height']*capture_scale:.0f}"
            )
        note = "  ·  ".join(note_parts)
        ok = timeline.AddMarker(offset, "Blue", name, note, 1, "")
        if ok:
            marker_count += 1
        else:
            print(f"  WARN: failed to add marker at frame {offset} ({name})")
    print(f"  {marker_count} markers added")

    print("\ndone — switch to Resolve. Add zoom/pan keyframes around the")
    print("blue click markers by hand for now; script-driven keyframes are")
    print("deferred to v1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
