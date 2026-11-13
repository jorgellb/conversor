// Servicio `migrateauth` (13): crea o actualiza las tablas de Better Auth antes de arrancar la web.
// Usa los mismos plugins que src/lib/auth.ts, que son los que definen el esquema.
import { betterAuth } from "better-auth";
import { getMigrations } from "better-auth/db/migration";
import { admin, jwt, magicLink } from "better-auth/plugins";
import pg from "pg";

const url = process.env.AUTH_DATABASE_URL || process.env.DATABASE_URL_WEB;
if (!url) {
  console.error("Falta AUTH_DATABASE_URL");
  process.exit(1);
}
const pool = new pg.Pool({ connectionString: url, max: 2 });
const options = {
  database: pool,
  secret: process.env.AUTH_SECRET || "solo-para-migrar",
  baseURL: process.env.BETTER_AUTH_URL || "http://localhost:3000",
  emailAndPassword: { enabled: true },
  plugins: [jwt(), admin(), magicLink({ sendMagicLink: async () => {} })],
};
betterAuth(options);
const { toBeCreated, toBeAdded, runMigrations } = await getMigrations(options);
if (!toBeCreated.length && !toBeAdded.length) {
  console.log("Esquema de autenticación al día");
} else {
  await runMigrations();
  console.log(`Migración de autenticación aplicada: ${toBeCreated.length} tablas nuevas, ${toBeAdded.length} con columnas nuevas`);
}
await pool.end();
