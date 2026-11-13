// Better Auth (2): correo y contraseña, enlace mágico, Google opcional, administración y JWT para la API.
import { betterAuth } from "better-auth";
import { nextCookies } from "better-auth/next-js";
import { admin, jwt, magicLink } from "better-auth/plugins";
import { Pool } from "pg";

import { sendMail } from "./mail";
import { SITE_NAME } from "./site";

function build() {
  const baseURL = (process.env.BETTER_AUTH_URL || "http://localhost:3000").replace(/\/$/, "");
  const google =
    process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET
      ? { google: { clientId: process.env.GOOGLE_CLIENT_ID, clientSecret: process.env.GOOGLE_CLIENT_SECRET } }
      : {};
  return betterAuth({
    appName: SITE_NAME,
    baseURL,
    secret: process.env.AUTH_SECRET,
    trustedOrigins: [baseURL],
    database: new Pool({ connectionString: process.env.AUTH_DATABASE_URL, max: 5 }),
    emailAndPassword: {
      enabled: true,
      requireEmailVerification: true,
      minPasswordLength: 10,
      sendResetPassword: async ({ user, url }) => {
        await sendMail(user.email, `${SITE_NAME}: cambiar la contraseña`, `Para elegir una contraseña nueva, abre este enlace:\n${url}\n\nSi no lo has pedido tú, ignora este correo.`);
      },
    },
    emailVerification: {
      sendOnSignUp: true,
      autoSignInAfterVerification: true,
      sendVerificationEmail: async ({ user, url }) => {
        await sendMail(user.email, `${SITE_NAME}: confirma tu correo`, `Confirma tu dirección abriendo este enlace:\n${url}`);
      },
    },
    socialProviders: google,
    user: { deleteUser: { enabled: true } },
    rateLimit: { enabled: true, window: 60, max: 30 },
    advanced: { ipAddress: { ipAddressHeaders: ["cf-connecting-ip", "x-forwarded-for"] } },
    plugins: [
      jwt({
        jwks: { keyPairConfig: { alg: "EdDSA", crv: "Ed25519" } },
        jwt: {
          issuer: baseURL,
          audience: baseURL,
          expirationTime: "15m",
          definePayload: ({ user }) => ({ email: user.email, email_verified: user.emailVerified, role: (user as { role?: string }).role ?? "user" }),
        },
      }),
      admin(),
      magicLink({
        sendMagicLink: async ({ email, url }) => {
          await sendMail(email, `${SITE_NAME}: tu enlace para entrar`, `Abre este enlace para entrar (caduca en 5 minutos):\n${url}`);
        },
      }),
      nextCookies(),
    ],
  });
}

let instance: ReturnType<typeof build> | null = null;

/** Se crea al primer uso: así `next build` no necesita base de datos ni secretos. */
export function getAuth() {
  instance ??= build();
  return instance;
}
