import type { Actions } from "../actions/instrumented.ts";
import { config } from "../shared/config.ts";

// 10–15s flow against a freshly-installed humr cluster:
//   land on Keycloak → log in dev/dev → walk the three setup pills
//   → poke the sidebar. Exercises clicks across the whole viewport
//   so the cursor compositor has interesting motion to interpolate.
export async function run(actions: Actions): Promise<void> {
  await actions.navigate(config.baseUrl);
  await actions.wait(1200, "settle-login");

  await actions.type("#username", "dev", "username");
  await actions.wait(200, "between-fields");
  await actions.type("#password", "dev", "password");
  await actions.wait(300, "before-submit");
  await actions.click("#kc-login", "sign-in");
  await actions.wait(2000, "post-login-load");

  await actions.click('button:has-text("Set up connections")', "pill-connections");
  await actions.wait(900, "view-connections");

  await actions.click('button:has-text("Set up a provider")', "pill-provider");
  await actions.wait(900, "view-provider");

  await actions.click('button:has-text("Add your first agent")', "pill-agent");
  await actions.wait(900, "view-agent");

  await actions.click('button:has-text("Settings")', "nav-settings");
  await actions.wait(800, "view-settings");

  await actions.click('button:has-text("Agents")', "nav-agents");
  await actions.wait(800, "final-hold");
}
