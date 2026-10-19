import { auth } from "./auth.js";

const email = process.env.ADMIN_EMAIL?.trim();
const password = process.env.ADMIN_PASSWORD;
const name = process.env.ADMIN_NAME?.trim() || "Admin";

if (!email || !password) {
  console.error("Set ADMIN_EMAIL and ADMIN_PASSWORD before creating an admin.");
  process.exit(1);
}

try {
  await auth.api.createUser({
    body: {
      email,
      password,
      name,
      role: "admin",
    },
  });
} catch (error) {
  const message = error instanceof Error ? error.message : "Could not create the admin user.";
  console.error(message);
  process.exit(1);
}

console.log(`Created admin ${email}`);
process.exit(0);
