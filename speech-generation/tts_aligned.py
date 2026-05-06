"""
tts_aligned.py — EXPERIMENTAL. Generate narration whose cue timings
match the click events of an existing recording.

NOT THE PRIMARY WORKFLOW. The default flow is "natural-pace audio +
human pacing the recording to it" — see POC_PLAN.md. This script is
kept around for the future scripted-scene case where exact cue→click
sync matters and human pacing isn't an option (e.g., automated CI
recordings, batch re-renders).

PROBLEM
    ElevenLabs (and Edge, and Kokoro) speak at a natural pace. The
    {{cue}} markers in the script fire at whatever moment the TTS
    decides — not at the moment the corresponding click happens in the
    recorded video. For a synced final without manual editing, cue
    at_ms must equal the click event's t.

SOLUTION
    Generate one segment per cue boundary, post-process by inserting
    silence between segments so cumulative cue at_ms lands exactly on
    the target click times. Optionally adjust per-segment speed (within
    ElevenLabs' 0.7–1.2 envelope) for tighter pacing on segments that
    would otherwise overshoot or leave large silences.

    Tradeoff: silence padding sounds unnatural in long doses, and speed
    shifts wobble prosody. For polished output prefer the natural-pace
    flow + manual trim in Resolve.

USAGE
    pip install elevenlabs
    export ELEVENLABS_API_KEY=sk_...

    python tts_aligned.py humr_test_script.txt \\
        --voice 2zGvynULFssveGrcP8hi \\
        --events ../out/events.json \\
        --label-map humr_test.labelmap.json \\
        --out humr_test_aligned

    Produces:
        humr_test_aligned.mp3            aligned audio
        humr_test_aligned.timings.json   cues at their EXACT target at_ms

LABEL MAP (--label-map JSON)
    Maps cue names in the script to click labels in events.json. The
    cue's target_at_ms is the click's t. Cues not in the map are anchored
    at the natural at_ms (no silence padding around them).

        {
          "sign_in":     "kc-login",
          "providers":   "Set up a provider",
          "connections": "Set up connections",
          "add_agent":   "Add your first agent",
          "settings":    "Settings",
          "agents":      "Agents"
        }

REQUIREMENTS
    - ffmpeg on PATH (for audio concat + silence insertion)
    - ELEVENLABS_API_KEY set
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


CUE_RE = re.compile(r"\{\{([a-z0-9_\-]+)\}\}")
WORD_RE = re.compile(r"\w+(?:['‘’]\w+)?")
VOICE_ID_RE = re.compile(r"^[A-Za-z0-9]{20}$")

DEFAULT_MODEL = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
SAMPLE_RATE = 44100


def split_by_cues(script: str) -> list[dict]:
    """Split a script into segments. Each segment carries the cue (if any)
    that fires AT THE END of its last word.

    Returns a list of {"text": str, "cue_at_end": str | None}. Empty-text
    segments (cue at very start, or two cues back-to-back) are kept so
    consecutive cues stack correctly.
    """
    segments: list[dict] = []
    last = 0
    for m in CUE_RE.finditer(script):
        text = script[last:m.start()]
        segments.append({"text": text, "cue_at_end": m.group(1)})
        last = m.end()
    tail = script[last:]
    segments.append({"text": tail, "cue_at_end": None})
    return segments


def find_click_t_ms(events: dict, label: str) -> float | None:
    """Find the t (ms) of the click event whose label matches. Match is
    case-insensitive, exact match preferred over substring.
    """
    label_lc = label.lower()
    exact: float | None = None
    sub: float | None = None
    for e in events.get("events", []):
        if e.get("kind") != "click":
            continue
        ev_label = (e.get("label") or "").lower()
        if ev_label == label_lc:
            exact = e["t"]
            break
        if sub is None and (label_lc in ev_label or ev_label in label_lc):
            sub = e["t"]
    return exact if exact is not None else sub


def resolve_voice(client, voice: str) -> tuple[str, str]:
    if VOICE_ID_RE.match(voice):
        return voice, voice
    page = client.voices.get_all()
    for v in page.voices:
        if v.name.lower() == voice.lower():
            return v.voice_id, v.name
    available = ", ".join(sorted(v.name for v in page.voices))
    raise ValueError(f"Voice {voice!r} not found. Available: {available}")


def generate_segment(client, voice_id: str, text: str, model: str, speed: float) -> tuple[bytes, float]:
    """Returns (audio_bytes, duration_ms). Skips empty/whitespace text."""
    from elevenlabs import VoiceSettings

    if not text.strip():
        return b"", 0.0

    response = client.text_to_speech.convert_with_timestamps(
        voice_id=voice_id,
        text=text,
        model_id=model,
        output_format=DEFAULT_OUTPUT_FORMAT,
        voice_settings=VoiceSettings(
            stability=0.5,
            similarity_boost=0.75,
            style=0.0,
            use_speaker_boost=True,
            speed=max(0.7, min(1.2, speed)),
        ),
    )
    audio = base64.b64decode(response.audio_base_64)
    ends = list(response.alignment.character_end_times_seconds)
    duration_ms = ends[-1] * 1000 if ends else 0.0
    return audio, duration_ms


def write_silence(path: Path, duration_ms: float) -> None:
    seconds = max(0.001, duration_ms / 1000)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=channel_layout=mono:sample_rate={SAMPLE_RATE}",
            "-t", f"{seconds:.3f}",
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            str(path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def concat_mp3s(parts: list[Path], output: Path) -> None:
    if not parts:
        raise RuntimeError("nothing to concat")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in parts:
            f.write(f"file '{p.resolve()}'\n")
        list_path = Path(f.name)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_path),
                "-c:a", "libmp3lame",
                "-b:a", "128k",
                "-ar", str(SAMPLE_RATE),
                str(output),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    finally:
        list_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("script", help="Path to script .txt file")
    parser.add_argument("--voice", required=True, help="ElevenLabs voice name or ID")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--events", required=True, help="Path to events.json")
    parser.add_argument(
        "--label-map",
        required=True,
        help="Path to JSON mapping {cue_name: click_label}",
    )
    parser.add_argument("--out", default="aligned", help="Output basename (no extension)")
    parser.add_argument(
        "--auto-speed",
        action="store_true",
        help="Adjust per-segment speed (clamped 0.7-1.2) before falling "
             "back to silence padding. Off by default — silence is more "
             "predictable than speed changes.",
    )
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        print("FAIL: ffmpeg not found on PATH", file=sys.stderr)
        return 2

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("FAIL: ELEVENLABS_API_KEY not set", file=sys.stderr)
        return 2

    script_text = Path(args.script).read_text(encoding="utf-8").strip()
    events = json.loads(Path(args.events).read_text(encoding="utf-8"))
    label_map: dict[str, str] = json.loads(Path(args.label_map).read_text(encoding="utf-8"))

    # Resolve cue → target_at_ms via the label map.
    cue_targets: dict[str, float] = {}
    print("cue → click mapping:")
    for cue, label in label_map.items():
        t_ms = find_click_t_ms(events, label)
        if t_ms is None:
            print(f"  WARN: cue {cue!r} → label {label!r} not found in events.json")
            continue
        cue_targets[cue] = float(t_ms)
        print(f"  {cue:14s} → {label!r:35s}  t={t_ms/1000:.2f}s")

    segments = split_by_cues(script_text)
    print(f"\nscript: {len(segments)} segments, "
          f"{sum(1 for s in segments if s['cue_at_end'])} cues")

    from elevenlabs import ElevenLabs
    client = ElevenLabs(api_key=api_key)
    voice_id, voice_name = resolve_voice(client, args.voice)
    print(f"voice: {voice_name} ({voice_id})")
    print(f"model: {args.model}\n")

    # Generate each segment at speed=1.0 first to learn natural duration,
    # then optionally regenerate with --auto-speed to better fit target.
    out_dir = Path(args.out).parent if Path(args.out).parent != Path() else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="tts_aligned_") as tmp:
        tmp_dir = Path(tmp)
        natural: list[tuple[bytes, float]] = []
        for i, seg in enumerate(segments):
            audio, dur = generate_segment(client, voice_id, seg["text"], args.model, 1.0)
            natural.append((audio, dur))
            cue = seg["cue_at_end"] or "—"
            print(f"  seg {i}: {len(seg['text']):3d} chars → {dur/1000:5.2f}s  (cue: {cue})")

        # Plan placement — for each segment, decide silence_before and
        # optional re-generate at non-default speed.
        print("\nplanning placement:")
        placements: list[dict] = []
        current_offset_ms = 0.0
        for i, seg in enumerate(segments):
            audio_bytes, natural_dur_ms = natural[i]
            seg_start_ms = current_offset_ms
            target_end_ms = cue_targets.get(seg["cue_at_end"]) if seg["cue_at_end"] else None

            if target_end_ms is None:
                # No target → just append at natural pace.
                placements.append({
                    "audio": audio_bytes,
                    "silence_after_ms": 0.0,
                })
                current_offset_ms += natural_dur_ms
                continue

            # We want seg_start + duration = target_end.
            # Two knobs: silence_after (>=0), or rate adjustment.
            desired_dur_ms = target_end_ms - seg_start_ms
            silence_after_ms = 0.0
            speed_adjusted = False

            if desired_dur_ms <= 0:
                print(
                    f"  seg {i}: cue {seg['cue_at_end']!r} target_at_ms="
                    f"{target_end_ms:.0f} but seg already starts at "
                    f"{seg_start_ms:.0f} → impossible, keeping natural pace"
                )
                current_offset_ms += natural_dur_ms
                placements.append({"audio": audio_bytes, "silence_after_ms": 0.0})
                continue

            if natural_dur_ms <= desired_dur_ms:
                silence_after_ms = desired_dur_ms - natural_dur_ms
                if args.auto_speed and silence_after_ms > 250:
                    # Try slowing down to consume some of that silence.
                    target_speed = natural_dur_ms / desired_dur_ms
                    target_speed = max(0.7, min(1.0, target_speed))
                    if abs(target_speed - 1.0) > 0.05:
                        print(f"  seg {i}: regen at speed={target_speed:.2f} "
                              f"to absorb {silence_after_ms:.0f}ms gap")
                        audio_bytes, natural_dur_ms = generate_segment(
                            client, voice_id, seg["text"], args.model, target_speed,
                        )
                        silence_after_ms = max(0.0, desired_dur_ms - natural_dur_ms)
                        speed_adjusted = True
                drift = silence_after_ms
                msg = f"+{drift:.0f}ms silence"
            else:
                # Natural is too long for the target gap. Speed up if allowed.
                if args.auto_speed:
                    target_speed = natural_dur_ms / desired_dur_ms
                    target_speed = max(1.0, min(1.2, target_speed))
                    print(f"  seg {i}: regen at speed={target_speed:.2f} "
                          f"to fit (natural overshoots by "
                          f"{natural_dur_ms - desired_dur_ms:.0f}ms)")
                    audio_bytes, natural_dur_ms = generate_segment(
                        client, voice_id, seg["text"], args.model, target_speed,
                    )
                    speed_adjusted = True
                if natural_dur_ms > desired_dur_ms:
                    print(
                        f"  seg {i}: WARN cue {seg['cue_at_end']!r} overshoots "
                        f"target by {natural_dur_ms - desired_dur_ms:.0f}ms — "
                        f"shorten the script for that segment, or lower speed limit"
                    )
                msg = f"-{natural_dur_ms - desired_dur_ms:.0f}ms over"

            placements.append({
                "audio": audio_bytes,
                "silence_after_ms": silence_after_ms,
            })
            current_offset_ms = seg_start_ms + natural_dur_ms + silence_after_ms
            extra = " (speed-adjusted)" if speed_adjusted else ""
            print(f"  seg {i}: cue {seg['cue_at_end']!r:14s} "
                  f"→ end @ {current_offset_ms/1000:5.2f}s "
                  f"(target {target_end_ms/1000:5.2f}s){extra}")

        # Materialize and concat.
        parts: list[Path] = []
        for i, pl in enumerate(placements):
            if pl["audio"]:
                seg_path = tmp_dir / f"seg{i:03d}.mp3"
                seg_path.write_bytes(pl["audio"])
                parts.append(seg_path)
            if pl["silence_after_ms"] > 0:
                silence_path = tmp_dir / f"sil{i:03d}.mp3"
                write_silence(silence_path, pl["silence_after_ms"])
                parts.append(silence_path)

        out_audio = Path(args.out).with_suffix(".mp3")
        print(f"\nconcat → {out_audio}")
        concat_mp3s(parts, out_audio)

    # Build aligned timings.json. For mapped cues, at_ms is the exact
    # target. Unmapped cues fall back to their natural at_ms (we don't
    # bother re-running alignment on the final audio — its timings are
    # determined by construction).
    aligned_cues = []
    cumulative_ms = 0.0
    for i, seg in enumerate(segments):
        natural_dur = natural[i][1]
        if seg["cue_at_end"]:
            target = cue_targets.get(seg["cue_at_end"])
            at_ms = target if target is not None else cumulative_ms + natural_dur
            aligned_cues.append({"name": seg["cue_at_end"], "at_ms": at_ms})
        # cumulative: add natural duration + planned silence_after
        cumulative_ms += natural_dur + placements[i]["silence_after_ms"]

    timings = {
        "voice": voice_name,
        "voice_id": voice_id,
        "model": args.model,
        "duration_ms": cumulative_ms,
        "cues": aligned_cues,
    }
    out_timings = Path(args.out).with_name(Path(args.out).name + ".timings.json")
    out_timings.write_text(json.dumps(timings, indent=2, ensure_ascii=False))
    print(f"wrote {out_timings}")

    print(f"\ntotal duration: {cumulative_ms/1000:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
