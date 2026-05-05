// Test whether CDP Page.startScreencast emits frames at viewport*DPR
// or at viewport*1. The answer dictates how we scale capture vs. layout.

import { chromium } from "playwright";
import sharp from "sharp";
import { writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";

async function probe(layout: { w: number; h: number }, dpr: number) {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: layout.w, height: layout.h },
    deviceScaleFactor: dpr,
    colorScheme: "dark",
  });
  const page = await context.newPage();
  await page.goto("data:text/html,<body style='margin:0;background:#152;color:#fff;font:48px sans-serif'><div style='width:100vw;height:100vh;display:flex;align-items:center;justify-content:center'>HELLO</div></body>");

  const cdp = await page.context().newCDPSession(page);
  let firstFrame: { data: string; w: number; h: number } | null = null;

  cdp.on("Page.screencastFrame", (params) => {
    if (firstFrame) return;
    const { data, metadata } = params;
    firstFrame = {
      data,
      w: metadata.deviceWidth ?? 0,
      h: metadata.deviceHeight ?? 0,
    };
    cdp.send("Page.screencastFrameAck", { sessionId: params.sessionId }).catch(() => {});
  });

  await cdp.send("Page.startScreencast", {
    format: "png",
    everyNthFrame: 1,
    maxWidth: 16384,
    maxHeight: 16384,
  });

  await page.waitForTimeout(800);
  await cdp.send("Page.stopScreencast").catch(() => {});

  if (!firstFrame) {
    console.log(`layout=${layout.w}x${layout.h} dpr=${dpr} → NO FRAME`);
    await browser.close();
    return;
  }
  // Decode the PNG to learn its actual pixel dimensions.
  const buf = Buffer.from((firstFrame as any).data, "base64");
  const meta = await sharp(buf).metadata();
  console.log(
    `layout=${layout.w}x${layout.h} dpr=${dpr} → frame ${meta.width}x${meta.height}` +
    ` (metadata.deviceWidth=${(firstFrame as any).w}, deviceHeight=${(firstFrame as any).h})`,
  );

  const out = resolve(process.cwd(), `out/.dpr/${layout.w}x${layout.h}@${dpr}.png`);
  await mkdir(resolve(process.cwd(), "out/.dpr"), { recursive: true });
  await writeFile(out, buf);

  await browser.close();
}

async function main() {
  await probe({ w: 1920, h: 1080 }, 1);
  await probe({ w: 1920, h: 1080 }, 2);
  await probe({ w: 1536, h: 864 }, 2);
  await probe({ w: 1280, h: 720 }, 2);
  await probe({ w: 1280, h: 720 }, 3);
}

main().catch((err) => { console.error(err); process.exit(1); });
