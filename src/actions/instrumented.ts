import type { Locator, Page } from "playwright";
import { config } from "../shared/config.ts";
import type { Logger } from "../recorder/logger.ts";

export class Actions {
  constructor(
    private readonly page: Page,
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
    const locator =
      typeof target === "string" ? this.page.locator(target) : target;
    await locator.waitFor({ state: "visible" });
    const bbox = await locator.boundingBox();
    if (!bbox) throw new Error(`No bounding box for ${label ?? "target"}`);
    const x = bbox.x + bbox.width / 2;
    const y = bbox.y + bbox.height / 2;
    this.logger.record({
      kind: "click",
      t: this.logger.now(),
      x,
      y,
      bbox,
      label,
      target: typeof target === "string" ? target : undefined,
    });
    await this.page.mouse.move(x, y, { steps: 20 });
    await this.page.mouse.click(x, y);
  }

  async type(target: Locator | string, text: string, label?: string): Promise<void> {
    const locator =
      typeof target === "string" ? this.page.locator(target) : target;
    await locator.waitFor({ state: "visible" });
    const startedAt = this.logger.now();
    await locator.click();
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
}
