// Quick exploration: open humr, log in, walk a few clicks, dump selectors.
// Not part of the recorder pipeline — used to learn the UI before authoring scenes.

import { chromium } from "playwright";
import { writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";

async function main() {
  const outDir = resolve(process.cwd(), "out/.probe");
  await mkdir(outDir, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 2560, height: 1440 },
    deviceScaleFactor: 1,
    colorScheme: "dark",
  });
  const page = await context.newPage();

  // tsx injects __name(fn, …) wrappers into source; stub it in the page context.
  await page.addInitScript(() => {
    (globalThis as unknown as { __name: <T>(fn: T) => T }).__name = (fn) => fn;
  });

  await page.goto("http://humr.localhost:4444/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(800);

  // Snapshot landing.
  await page.screenshot({ path: resolve(outDir, "01-landing.png") });
  await writeFile(resolve(outDir, "01-landing.html"), await page.content());
  console.log("title (landing):", await page.title());
  console.log("url (landing):", page.url());

  // Look for inputs/buttons we might use to log in.
  const summary = await page.evaluate(() => {
    const list = (selector: string) =>
      Array.from(document.querySelectorAll(selector)).slice(0, 15).map((el) => {
        const e = el as HTMLElement;
        const r = e.getBoundingClientRect();
        return {
          tag: e.tagName.toLowerCase(),
          id: e.id || undefined,
          name: (e as HTMLInputElement).name || undefined,
          type: (e as HTMLInputElement).type || undefined,
          placeholder: (e as HTMLInputElement).placeholder || undefined,
          text: (e.innerText || "").trim().slice(0, 60) || undefined,
          aria: e.getAttribute("aria-label") || undefined,
          x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
          visible: r.width > 0 && r.height > 0,
        };
      });
    return {
      inputs: list("input"),
      buttons: list("button"),
      links: list("a").filter(a => (a.text?.length ?? 0) > 0),
    };
  });
  console.log("=== landing inputs ===");
  console.log(JSON.stringify(summary.inputs, null, 2));
  console.log("=== landing buttons ===");
  console.log(JSON.stringify(summary.buttons, null, 2));
  console.log("=== landing links ===");
  console.log(JSON.stringify(summary.links.slice(0, 8), null, 2));

  // Try to log in.
  const usernameInput = await page.$('input[name="username"], input[type="email"], input[name="email"], input[id*="user" i]');
  const passwordInput = await page.$('input[type="password"]');
  if (usernameInput && passwordInput) {
    await usernameInput.fill("dev");
    await passwordInput.fill("dev");
    const submit =
      (await page.$('button[type="submit"]')) ??
      (await page.$('input[type="submit"]')) ??
      (await page.$('button:has-text("Sign in"), button:has-text("Log in"), button:has-text("Login")'));
    if (submit) {
      await Promise.all([
        page.waitForLoadState("networkidle").catch(() => {}),
        submit.click(),
      ]);
      await page.waitForTimeout(1500);
    }
  }

  await page.screenshot({ path: resolve(outDir, "02-after-login.png") });
  await writeFile(resolve(outDir, "02-after-login.html"), await page.content());
  console.log("title (after login):", await page.title());
  console.log("url (after login):", page.url());

  const post = await page.evaluate(() => {
    const list = (selector: string) =>
      Array.from(document.querySelectorAll(selector)).slice(0, 25).map((el) => {
        const e = el as HTMLElement;
        const r = e.getBoundingClientRect();
        return {
          tag: e.tagName.toLowerCase(),
          id: e.id || undefined,
          text: (e.innerText || "").trim().slice(0, 60) || undefined,
          aria: e.getAttribute("aria-label") || undefined,
          href: (e as HTMLAnchorElement).href || undefined,
          x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
          visible: r.width > 0 && r.height > 0,
        };
      });
    return {
      navs: list("nav a, [role='navigation'] a, header a, aside a"),
      buttons: list("button"),
      links: list("a"),
    };
  });
  console.log("=== post-login navs ===");
  console.log(JSON.stringify(post.navs.slice(0, 12), null, 2));
  console.log("=== post-login buttons ===");
  console.log(JSON.stringify(post.buttons.slice(0, 12), null, 2));

  await browser.close();
}

main().catch((err) => { console.error(err); process.exit(1); });
