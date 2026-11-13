import Link from "next/link";

// Rutas fuera de /es y /en.
export default function NotFound() {
  return (
    <html lang="es">
      <body style={{ fontFamily: "system-ui", padding: "2rem" }}>
        <h1>Página no encontrada</h1>
        <p>
          <Link href="/es">Volver al inicio</Link> · <Link href="/en">Back to home</Link>
        </p>
      </body>
    </html>
  );
}
