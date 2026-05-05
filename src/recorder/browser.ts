import { chromium, type BrowserContext, type Page } from "playwright";
import { config } from "../shared/config.ts";

export type BrowserSession = {
  context: BrowserContext;
  page: Page;
  close: () => Promise<void>;
};

export async function openBrowser(): Promise<BrowserSession> {
  const browser = await chromium.launch({
    headless: true,
    args: ["--hide-scrollbars", "--force-color-profile=srgb"],
  });
  const context = await browser.newContext({
    viewport: config.viewport,
    deviceScaleFactor: 1,
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
