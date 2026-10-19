import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { config as loadDotenv } from "dotenv";

/** Load the repository `.env` when it exists. Existing process env vars win. */
export function loadRootEnv(): void {
  let directory = dirname(fileURLToPath(import.meta.url));
  for (let depth = 0; depth < 6; depth += 1) {
    if (existsSync(resolve(directory, "docker-compose.yml"))) {
      loadDotenv({ path: resolve(directory, ".env") });
      return;
    }
    directory = resolve(directory, "..");
  }
}
