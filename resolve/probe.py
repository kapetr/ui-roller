"""
probe.py — verify DaVinci Resolve scripting connectivity.

USAGE
    1. Open DaVinci Resolve.
    2. Open or create a project (any project will do).
    3. Run: python3 resolve/probe.py

If the connection works, this prints product name, version, and current
project. If it fails, the error message points at what to fix (Resolve
not running, env vars wrong, Python bitness, etc.).

Resolve must be running. Scripting access must be enabled in
Resolve > Preferences > System > General > External scripting using = Local.
"""

from __future__ import annotations
import os
import sys

DEFAULT_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
DEFAULT_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

os.environ.setdefault("RESOLVE_SCRIPT_API", DEFAULT_API)
os.environ.setdefault("RESOLVE_SCRIPT_LIB", DEFAULT_LIB)
sys.path.insert(0, os.path.join(os.environ["RESOLVE_SCRIPT_API"], "Modules"))


def main() -> int:
    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except ImportError as e:
        print(f"FAIL: cannot import DaVinciResolveScript: {e}", file=sys.stderr)
        print(
            f"      Check RESOLVE_SCRIPT_API={os.environ.get('RESOLVE_SCRIPT_API')!r} "
            f"and RESOLVE_SCRIPT_LIB={os.environ.get('RESOLVE_SCRIPT_LIB')!r}",
            file=sys.stderr,
        )
        return 2

    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        print("FAIL: scriptapp returned None — Resolve isn't running, or", file=sys.stderr)
        print("      external scripting is disabled in Resolve preferences.", file=sys.stderr)
        return 3

    print(f"product:  {resolve.GetProductName()}")
    print(f"version:  {resolve.GetVersionString()}")
    print(f"page:     {resolve.GetCurrentPage()}")

    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if project is None:
        print("project:  (none open)")
        print("\nNote: open a project before running to-resolve.py.")
        return 0

    print(f"project:  {project.GetName()}")
    timeline = project.GetCurrentTimeline()
    if timeline is None:
        print("timeline: (none)")
    else:
        print(f"timeline: {timeline.GetName()} ({timeline.GetEndFrame() - timeline.GetStartFrame()} frames)")

    print("\nOK — Resolve scripting is reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
