# Gotenberg (12.2)

Dos instancias de la imagen oficial `gotenberg/gotenberg:8.39.0`; los flags van en `command:` de cada Compose.

| Instancia | Recibe | Red | Flags de salida |
| --- | --- | --- | --- |
| `gotenberg` | archivos de usuarios (Office, HTML subido) | solo `internal` | `--chromium-deny-public-ips=true`, `--chromium-deny-private-ips=true`, `--libreoffice-deny-public-ips=true`, `--libreoffice-deny-private-ips=true` |
| `gotenbergweb` (web-a-pdf) | solo URL, nunca archivos | solo `webrender` (D-34) | `--chromium-proxy-server=http://egressweb:4750`, `--libreoffice-disable-routes=true` |

En las dos: `--api-download-from-deny-public-ips=true`, `--api-download-from-deny-private-ips=true`,
`--webhook-deny-public-ips=true` y `--webhook-deny-private-ips=true`. Desde la 8.32 los filtros de salida vienen
desactivados por defecto, así que no se pueden quitar. Comprueba los nombres al subir de versión
(`docker run --rm gotenberg/gotenberg:<versión> gotenberg --help`).
