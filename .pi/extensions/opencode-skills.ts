import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import path from "node:path";

/**
 * Bridges opencode skills (.opencode/skills/) into pi's skill discovery.
 *
 * Uses resources_discover to add .opencode/skills as a skillPath,
 * so pi loads each SKILL.md directory as a native skill with
 * /skill:name command support and system prompt descriptions.
 */
export default function (pi: ExtensionAPI) {
  pi.on("resources_discover", async (event, _ctx) => {
    const skillDir = path.join(event.cwd, ".opencode", "skills");

    return {
      skillPaths: [skillDir],
    };
  });
}
