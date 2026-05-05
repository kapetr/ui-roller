// Test the "physical viewport big + body zoom" trick: the page lays out as
// if it were `logical` CSS pixels wide, but the framebuffer is `logical*scale`.
// Verifies (a) capture resolution, (b) whether boundingClientRect coords are
// in pre-zoom or post-zoom pixels (compositor needs to know).

import { chromium, type Page } from "playwright";
import sharp from "sharp";
import { writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";

async function probe(label: string, logical: { w: number; h: number }, scale: number) {
  const physical = { w: logical.w * scale, h: logical.h * scale };
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: physical.w, height: physical.h },
    deviceScaleFactor: 1,
    colorScheme: "dark",
  });
  const page = await context.newPage();

  // Inject body { zoom } before any page script.
  await page.addInitScript((s) => {
    const id = "__recorder_zoom_style";
    if (document.getElementById(id)) return;
    const style = document.createElement("style");
    style.id = id;
    style.textContent = `html, body { zoom: ${s}; }`;
    (document.head ?? document.documentElement).appendChild(style);
  }, scale);

  // tsx __name shim for any later page.evaluate calls.
  await page.addInitScript(() => {
    (globalThis as unknown as { __name: <T>(fn: T) => T }).__name = (fn) => fn;
  });

  await page.goto("http://humr.localhost:4444/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(800);

  // Login.
  await page.fill("#username", "dev");
  await page.fill("#password", "dev");
  await Promise.all([
    page.waitForLoadState("networkidle").catch(() => {}),
    page.click("#kc-login"),
  ]);
  await page.waitForTimeout(1500);

  // Sample a known button's bbox.
  const probe = await page.evaluate(() => {
    const sel = 'button';
    const btn = Array.from(document.querySelectorAll(sel))
      .find((el) => (el as HTMLElement).innerText?.includes("Set up a provider"));
    if (!btn) return null;
    const r = (btn as HTMLElement).getBoundingClientRect();
    return {
      bcr: { x: r.x, y: r.y, w: r.width, h: r.height },
      windowInner: { w: window.innerWidth, h: window.innerHeight },
      docClient: { w: document.documentElement.clientWidth, h: document.documentElement.clientHeight },
      dpr: window.devicePixelRatio,
    };
  });

  // Take a screencast frame.
  const cdp = await page.context().newCDPSession(page);
  let frame: { data: string; meta: { w: number; h: number } } | null = null;
  cdp.on("Page.screencastFrame", (params) => {
    if (frame) return;
    frame = { data: params.data, meta: { w: params.metadata.deviceWidth ?? 0, h: params.metadata.deviceHeight ?? 0 } };
    cdp.send("Page.screencastFrameAck", { sessionId: params.sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", {
    format: "png",
    everyNthFrame: 1,
    maxWidth: 16384,
    maxHeight: 16384,
  });
  await page.waitForTimeout(500);
  await cdp.send("Page.stopScreencast").catch(() => {});

  let pngSize = "(no frame)";
  if (frame) {
    const buf = Buffer.from((frame as any).data, "base64");
    const meta = await sharp(buf).metadata();
    pngSize = `${meta.width}×${meta.height}`;
    const out = resolve(process.cwd(), `out/.zoom/${label}.png`);
    await mkdir(resolve(process.cwd(), "out/.zoom"), { recursive: true });
    await writeFile(out, buf);
  }

  console.log(
    `${label}: physical=${physical.w}×${physical.h} logical=${logical.w}×${logical.h} scale=${scale}\n` +
      `  innerSize=${JSON.stringify(probe?.windowInner)} docClient=${JSON.stringify(probe?.docClient)} dpr=${probe?.dpr}\n` +
      `  pill bcr=${JSON.stringify(probe?.bcr)}\n` +
      `  screencast frame=${pngSize}`,
  );

  await browser.close();
}

async function main() {
  await probe("baseline-2k", { w: 2560, h: 1440 }, 1);
  await probe("flat-1080p", { w: 1920, h: 1080 }, 1);
  await probe("zoom1.5-1080p-logical", { w: 1920, h: 1080 }, 1.5);
  await probe("zoom2-1080p-logical", { w: 1920, h: 1080 }, 2);
}

main().catch((err) => { console.error(err); process.exit(1); });
