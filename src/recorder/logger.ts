import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import type { Event, EventLog } from "../shared/events.ts";

export class Logger {
  private readonly events: Event[] = [];
  private readonly startedAtMs = Date.now();
  private readonly startedAtIso = new Date().toISOString();

  constructor(
    private readonly viewport: { width: number; height: number },
    private readonly captureScale: number,
  ) {}

  now(): number {
    return Date.now() - this.startedAtMs;
  }

  record(event: Event): void {
    this.events.push(event);
  }

  async write(path: string): Promise<void> {
    const log: EventLog = {
      startedAt: this.startedAtIso,
      viewport: this.viewport,
      captureScale: this.captureScale,
      events: this.events,
    };
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, JSON.stringify(log, null, 2));
  }
}
