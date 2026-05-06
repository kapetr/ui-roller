import type { Locator, Page } from "playwright";
import { config } from "../shared/config.ts";
import type { Logger } from "../recorder/logger.ts";

export type ActionOptions = {
  // Free-form label written to events.json — useful for analytics.
  label?: string;
  // Cue name from the speech timings file. The action waits until the
  // cue's at_ms before firing (or fires immediately if we're already
  // past it; drift is logged either way).
  cue?: string;
};

// Things waitFor can wait on. Composable: pass any subset, all must hold.
export type WaitConditions = {
  // CSS / Playwright selector that must be visible.
  visible?: string;
  // Substring that must appear inside an element matching `in` (or anywhere
  // on the page if `in` is omitted).
  text?: string;
  in?: string;
  // True = wait until the page reports networkidle.
  networkIdle?: boolean;
  // Arbitrary predicate evaluated in the page context. Polled every ~50 ms.
  predicate?: () => boolean | Promise<boolean>;
  // Hard ceiling, ms. Default 30 s.
  timeoutMs?: number;
  // Optional reason recorded into events.json for the eventual wait entry.
  reason?: string;
};

const normalizeOpts = (
  opts: string | ActionOptions | undefined,
): ActionOptions => (typeof opts === "string" ? { label: opts } : opts ?? {});

export class Actions {
  constructor(
    public readonly page: Page,
    private readonly logger: Logger,
  ) {}

  async navigate(url: string): Promise<void> {
    this.logger.record({ kind: "navigate", t: this.logger.now(), url });
    await this.page.goto(url, { waitUntil: "domcontentloaded" });
  }

  async clickFirst(
    selector: string,
    opts?: string | ActionOptions,
  ): Promise<void> {
    return this.click(this.page.locator(selector).first(), opts);
  }

  async click(
    target: Locator | string,
    opts?: string | ActionOptions,
  ): Promise<void> {
    const { label, cue } = normalizeOpts(opts);

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

    // Cue floor: don't click before narration reaches its mark.
    await this.waitUntilCue(cue);

    // Cursor floor: hold long enough for the compositor's eased path to
    // visually arrive at this target. Page mouse and visible cursor both
    // land here at the moment we log the click event — no drift, no
    // ghostly hovers ahead of the cursor.
    await sleep(config.compositor.cursor.travelMs);

    this.logger.record({
      kind: "click",
      t: this.logger.now(),
      x,
      y,
      bbox,
      label,
      target: typeof target === "string" ? target : undefined,
      cue,
    });
    await this.page.mouse.move(x, y, { steps: 20 });
    await this.page.mouse.click(x, y);
  }

  async hover(
    target: Locator | string,
    opts?: string | ActionOptions,
  ): Promise<void> {
    const { label, cue } = normalizeOpts(opts);
    const locator =
      typeof target === "string"
        ? this.page.locator(`${target} >> visible=true`).first()
        : target;
    await locator.waitFor({ state: "visible" });
    const bbox = await locator.boundingBox();
    if (!bbox) throw new Error(`No bounding box for ${label ?? "hover"}`);
    const x = bbox.x + bbox.width / 2;
    const y = bbox.y + bbox.height / 2;

    await this.waitUntilCue(cue);
    await sleep(config.compositor.cursor.travelMs);

    this.logger.record({
      kind: "move",
      t: this.logger.now(),
      x,
      y,
      label,
      target: typeof target === "string" ? target : undefined,
      cue,
    });
    await this.page.mouse.move(x, y, { steps: 20 });
  }

  async type(
    target: Locator | string,
    text: string,
    opts?: string | ActionOptions,
  ): Promise<void> {
    const { label, cue } = normalizeOpts(opts);
    // Click the input first so the cursor visibly lands on it before typing.
    await this.click(target, {
      label: label ? `${label}-focus` : undefined,
      cue,
    });
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

  // Fixed-duration breath. Use sparingly — semantic waits scale better.
  async wait(durationMs: number, label?: string): Promise<void> {
    this.logger.record({
      kind: "wait",
      t: this.logger.now(),
      durationMs,
      label,
    });
    await this.page.waitForTimeout(durationMs);
  }

  // Semantic wait: returns when all supplied conditions hold (or throws on
  // timeout). Logs a wait event with the elapsed duration and the reason
  // so events.json reflects what we were really waiting on.
  async waitFor(conditions: WaitConditions): Promise<void> {
    const startedAt = this.logger.now();
    const timeoutMs = conditions.timeoutMs ?? 30_000;

    if (conditions.visible) {
      await this.page
        .locator(`${conditions.visible} >> visible=true`)
        .first()
        .waitFor({ state: "visible", timeout: timeoutMs });
    }
    if (conditions.text) {
      const locator = conditions.in
        ? this.page.locator(conditions.in)
        : this.page.locator("body");
      await locator
        .filter({ hasText: conditions.text })
        .first()
        .waitFor({ state: "visible", timeout: timeoutMs });
    }
    if (conditions.networkIdle) {
      await this.page.waitForLoadState("networkidle", { timeout: timeoutMs });
    }
    if (conditions.predicate) {
      await this.page.waitForFunction(conditions.predicate, undefined, {
        timeout: timeoutMs,
        polling: 50,
      });
    }

    const elapsed = this.logger.now() - startedAt;
    this.logger.record({
      kind: "wait",
      t: startedAt,
      durationMs: elapsed,
      reason: conditions.reason ?? describeConditions(conditions),
    });
  }

  // Block until the named cue's at_ms is reached. No-op if already past.
  // Drift is recorded so the audio assembler can decide what to do later.
  private async waitUntilCue(name: string | undefined): Promise<void> {
    if (!name) return;
    const target = this.logger.cueTime(name);
    if (target === undefined) {
      throw new Error(
        `Cue "${name}" not found in timings file. ` +
          `Did you forget to load it, or misspell the cue?`,
      );
    }
    const now = this.logger.now();
    if (now < target) await sleep(target - now);
    this.logger.recordCueDrift(name, target, this.logger.now());
  }
}

function describeConditions(c: WaitConditions): string {
  const parts: string[] = [];
  if (c.visible) parts.push(`visible:${c.visible}`);
  if (c.text) parts.push(`text:"${c.text}"${c.in ? ` in ${c.in}` : ""}`);
  if (c.networkIdle) parts.push("networkIdle");
  if (c.predicate) parts.push("predicate");
  return parts.join(" + ") || "<none>";
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
