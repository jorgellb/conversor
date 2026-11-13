// Healthcheck del contenedor web (13).
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ok" });
}
