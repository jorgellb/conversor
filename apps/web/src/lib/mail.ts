// Correo transaccional por SMTP (SMTP_URL). Sin SMTP en desarrollo, el enlace se escribe en el log del servidor.
import nodemailer, { type Transporter } from "nodemailer";

let transport: Transporter | null = null;

export async function sendMail(to: string, subject: string, text: string): Promise<void> {
  const url = process.env.SMTP_URL;
  const from = process.env.MAIL_FROM || "no-responder@ejemplo.test";
  if (!url) {
    console.info(JSON.stringify({ level: "info", msg: "correo sin SMTP (desarrollo)", to, subject, text }));
    return;
  }
  transport ??= nodemailer.createTransport(url);
  await transport.sendMail({ from, to, subject, text });
}
