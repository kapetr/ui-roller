import type { Actions } from "../actions/instrumented.ts";
import { config } from "../shared/config.ts";

export async function run(actions: Actions): Promise<void> {
  await actions.navigate(config.baseUrl);
  await actions.wait(1500, "settle");
  await actions.clickFirst(
    "button, a, input[type='submit']",
    "first-interactive",
  );
  await actions.wait(800, "post-click-hold");
}
