import { getMigrations } from "better-auth/db/migration";

import { auth } from "./auth.js";

const { toBeCreated, toBeAdded, runMigrations } = await getMigrations(auth.options);

if (toBeCreated.length === 0 && toBeAdded.length === 0) {
  console.log("Better Auth schema is up to date.");
} else {
  await runMigrations();
  if (toBeCreated.length > 0) {
    console.log(`Created Better Auth tables: ${toBeCreated.map((table) => table.table).join(", ")}`);
  }
  if (toBeAdded.length > 0) {
    console.log(`Updated Better Auth tables: ${toBeAdded.map((table) => table.table).join(", ")}`);
  }
}

process.exit(0);
