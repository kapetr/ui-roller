import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import type {
  ActualTimings,
  CueDrift,
  Event,
  EventLog,
  SpeechCue,
} from "../shared/events.ts";

export class Logger {
  private readonly events: Event[] = [];
  private readonly drift: CueDrift[] = [];
  private startedAtMs = Date.now();
  private readonly startedAtIso = new Date().toISOString();
  // Indexed cue lookup. Empty when no timings file is loaded.
  private readonly cueAtMs: Map<string, number>;

  constructor(
    private readonly viewport: { width: number; height: number },
    private readonly captureScale: number,
    cues: SpeechCue[] = [],
  ) {
    this.cueAtMs = new Map(cues.map((c) => [c.name, c.at_ms]));
  }

  now(): number {
    return Date.now() - this.startedAtMs;
  }

  // Re-zero the logger to a wall-clock instant — typically the first
  // screencast frame's arrival time. Existing event timestamps are
  // shifted so the timeline stays consistent. Subsequent now() calls
  // return values relative to the new zero.
  alignTo(wallMs: number): number {
    const offset = wallMs - this.startedAtMs;
    if (offset === 0) return 0;
    for (const e of this.events) e.t -= offset;
    for (const c of this.drift) c.actualAtMs -= offset;
    this.startedAtMs = wallMs;
    return offset;
  }

  cueTime(name: string): number | undefined {
    return this.cueAtMs.get(name);
  }

  recordCueDrift(name: string, intendedAtMs: number, actualAtMs: number): void {
    this.drift.push({
      name,
      intendedAtMs,
      actualAtMs,
      driftMs: actualAtMs - intendedAtMs,
    });
  }

  record(event: Event): void {
    this.events.push(event);
  }

  async write(eventsPath: string, actualTimingsPath?: string): Promise<void> {
    const log: EventLog = {
      startedAt: this.startedAtIso,
      viewport: this.viewport,
      captureScale: this.captureScale,
      events: this.events,
    };
    await mkdir(dirname(eventsPath), { recursive: true });
    await writeFile(eventsPath, JSON.stringify(log, null, 2));

    if (actualTimingsPath && this.drift.length > 0) {
      const timings: ActualTimings = {
        startedAt: this.startedAtIso,
        durationMs: this.now(),
        cues: this.drift,
      };
      await writeFile(actualTimingsPath, JSON.stringify(timings, null, 2));
    }
  }
}
