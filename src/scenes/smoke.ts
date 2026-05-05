import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
import type { Actions } from "../actions/instrumented.ts";

export async function run(actions: Actions): Promise<void> {
  const fixture = pathToFileURL(
    resolve(process.cwd(), "fixtures/smoke.html"),
  ).href;
  await actions.navigate(fixture);
  await actions.wait(500, "settle");
  await actions.click("#primary", "primary-button");
  await actions.wait(500, "post-click-hold");
}
