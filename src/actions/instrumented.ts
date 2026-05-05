import type { Locator, Page } from "playwright";
import { config } from "../shared/config.ts";
import type { Logger } from "../recorder/logger.ts";
import { easeMove } from "../compositor/easing.ts";
import { interpolatePosition } from "../compositor/cursor-path.ts";

export class Actions {
  private lastMouse: { x: number; y: number } | null = null;

  constructor(
    public readonly page: Page,
    private readonly logger: Logger,
  ) {}

  async navigate(url: string): Promise<void> {
    this.logger.record({ kind: "navigate", t: this.logger.now(), url });
    await this.page.goto(url, { waitUntil: "domcontentloaded" });
  }

  async clickFirst(selector: string, label?: string): Promise<void> {
    return this.click(this.page.locator(selector).first(), label);
  }

  async click(target: Locator | string, label?: string): Promise<void> {
    // Strings get a `:visible` filter so duplicate hidden mobile/aria-labelled
    // variants don't trigger Playwright's strict-mode violation. Pass a pre-
    // narrowed Locator (e.g. page.getByRole(...)) when you need finer control.
    const locator =
      typeof target === "string"
        ? this.page.locator(`${target} >> visible=true`).first()
        : target;
    await locator.waitFor({ state: "visible" });
    const bbox = await locator.boundingBox();
    if (!bbox) throw new Error(`No bounding box for ${label ?? "target"}`);
    const x = bbox.x + bbox.width / 2;
    const y = bbox.y + bbox.height / 2;

    // Drive the page mouse along the same eased + curved path the compositor
    // will draw. Without this, hover state on the underlying capture lingers
    // at the previous click position while the visible cursor moves on,
    // which reads as ghostly hovers desynced from the cursor.
    await this.driveCursor(x, y);

    this.logger.record({
      kind: "click",
      t: this.logger.now(),
      x,
      y,
      bbox,
      label,
      target: typeof target === "string" ? target : undefined,
    });
    await this.page.mouse.click(x, y);
  }

  async type(target: Locator | string, text: string, label?: string): Promise<void> {
    // Click the input first so there's a visible cursor anchor at the field
    // (otherwise the cursor jumps from wherever it was to the *next* click,
    // which makes typing look like the cursor is psychic about its target).
    await this.click(target, label ? `${label}-focus` : undefined);
    const startedAt = this.logger.now();
    const locator =
      typeof target === "string"
        ? this.page.locator(`${target} >> visible=true`).first()
        : target;
    await locator.pressSequentially(text, { delay: config.typing.delayMs });
    this.logger.record({
      kind: "type",
      t: startedAt,
      text,
      durationMs: this.logger.now() - startedAt,
      label,
    });
  }

  async wait(durationMs: number, label?: string): Promise<void> {
    this.logger.record({
      kind: "wait",
      t: this.logger.now(),
      durationMs,
      label,
    });
    await this.page.waitForTimeout(durationMs);
  }

  // Drives page.mouse along the same trajectory the compositor renders so
  // both layers stay in lockstep.
  private async driveCursor(targetX: number, targetY: number): Promise<void> {
    if (this.lastMouse === null) {
      // First action — teleport. The compositor's `preroll: "first"` already
      // parks the visible cursor at the first anchor, so a synced teleport
      // here keeps both layers off-screen-then-on at t=0.
      await this.page.mouse.move(targetX, targetY);
      this.lastMouse = { x: targetX, y: targetY };
      return;
    }

    const start = this.lastMouse;
    const target = { x: targetX, y: targetY };
    // Mark the start of the travel in the event log. The compositor reads
    // this `move` event as an eager anchor — between it and the upcoming
    // click, the cursor eases over the *actual* gap rather than capping at
    // travelMs. That removes the lag introduced by mouse.move IPC overrun.
    this.logger.record({
      kind: "move",
      t: this.logger.now(),
      x: start.x,
      y: start.y,
    });

    const travelMs = config.compositor.cursor.travelMs;
    // Each Playwright mouse.move IPC round-trip is ~10-70ms depending on page
    // load. Issuing 48 single-step calls would tie travel speed to that
    // overhead. Instead carve the curve into a handful of sub-segments and
    // use Playwright's `steps:` option to fan out smooth linear interpolation
    // between them within a single IPC. ~8 segments × 6 steps gives 48
    // mouse events with 8× less round-trip cost.
    const subSegments = 8;
    const stepsPerSegment = 6;
    const curveOpts = {
      curveAmount: config.compositor.cursor.curveAmount,
      curveMaxOffset: config.compositor.cursor.curveMaxOffsetCss,
      curveMinDistance: config.compositor.cursor.curveMinDistanceCss,
    };

    const startWall = Date.now();
    for (let i = 1; i <= subSegments; i++) {
      const u = i / subSegments;
      const k = easeMove(u);
      const pos = interpolatePosition(start, target, k, curveOpts);
      await this.page.mouse.move(pos.x, pos.y, { steps: stepsPerSegment });

      // Pace against wall-clock so total motion takes ~travelMs.
      const targetElapsed = (i / subSegments) * travelMs;
      const actualElapsed = Date.now() - startWall;
      const wait = targetElapsed - actualElapsed;
      if (wait > 1) await sleep(wait);
    }

    this.lastMouse = target;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
