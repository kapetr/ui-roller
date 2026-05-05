import { chromium, type BrowserContext, type Page } from "playwright";
import { config } from "../shared/config.ts";

export type BrowserSession = {
  context: BrowserContext;
  page: Page;
  close: () => Promise<void>;
};

export async function openBrowser(): Promise<BrowserSession> {
  // --force-device-scale-factor is the magic knob: page lays out at the
  // CSS viewport size (so UI elements stay HD-sized), but Chromium rasterizes
  // at viewport × DSR — and CDP screencast emits at the rasterized size.
  // Without this flag, deviceScaleFactor on the context is a no-op for screencast.
  const browser = await chromium.launch({
    headless: true,
    args: [
      "--hide-scrollbars",
      "--force-color-profile=srgb",
      `--force-device-scale-factor=${config.captureScale}`,
      "--high-dpi-support=1",
    ],
  });
  const context = await browser.newContext({
    viewport: config.viewport,
    deviceScaleFactor: config.captureScale,
    colorScheme: "dark",
  });
  const page = await context.newPage();

  return {
    context,
    page,
    async close() {
      await page.close().catch(() => {});
      await context.close().catch(() => {});
      await browser.close().catch(() => {});
    },
  };
}
