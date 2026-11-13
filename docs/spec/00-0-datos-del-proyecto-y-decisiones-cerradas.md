## 0. Datos del proyecto y decisiones cerradas

Sustituye estos valores antes de empezar. Si al recibir este documento alguno sigue entre llaves, usa los valores de prueba de la sección 0.1, continúa y no publiques nada:

| Variable | Valor |
| --- | --- |
| `{{PRODUCTO}}` | Nombre comercial |
| `{{DOMINIO}}` | Dominio principal, por ejemplo `ejemplo.com` |
| `{{EMAIL_ADMIN}}` | Correo del primer administrador |

Dominios:

| Uso | Dominio |
| --- | --- |
| Web | `{{DOMINIO}}` |
| API pública | `api.{{DOMINIO}}` |
| Subidas reanudables (tus) | `upload.{{DOMINIO}}` |
| Descargas firmadas | `files.{{DOMINIO}}` |

Decisiones ya tomadas (no las cambies sin anotarlo en `docs/DECISIONS.md`):

1. **Un solo VPS** con Coolify v4. Todo el stack corre en ese servidor.
2. **Almacenamiento propio en disco del VPS. No hay S3** de ningún tipo (ni SeaweedFS, ni MinIO, ni servicios externos). Los archivos viven en un volumen local compartido por los servicios.
3. **IA solo con modelos gratuitos de OpenRouter** (`:free`), con un presupuesto global de 1.000 peticiones al día y 20 por minuto. Lo que se pueda hacer en local (embeddings, transcripción, voz, OCR) se hace en local para no gastar peticiones.
4. **Código cerrado**: prohibido enlazar librerías AGPL (sección 11).
5. Idiomas: español de España (por defecto) e inglés.
6. Pagos con Stripe en modo test, detrás de una interfaz `PaymentProvider`.
7. Delante de todo, Cloudflare (proxy, WAF y Turnstile).
8. **Paridad funcional con PDF24:**
   - Cada herramienta web de tools.pdf24.org tiene aquí un equivalente con, como mínimo, sus opciones (sección 7.23 y Anexo A).
   - La paridad es de funciones: no copies textos, diseños, plantillas ni marca de PDF24.

### 0.1 Lo que aporta el propietario y cuándo

No puedes crear cuentas, comprar nada ni aceptar condiciones de terceros. Trabaja con dobles locales hasta que el propietario aporte cada entrada y no bloquees el cierre técnico de una fase por su ausencia (sección 1.3).

| Entrada | La necesitas para | Mientras no exista |
| --- | --- | --- |
| Valores de `{{PRODUCTO}}`, `{{DOMINIO}}` y `{{EMAIL_ADMIN}}` | Textos, dominios y correo | `Producto Demo`, `ejemplo.test` y `admin@ejemplo.test`; no publiques nada |
| VPS con acceso SSH, Coolify instalado y un token de la API de Coolify | Cierre operativo de cada fase | Solo cierre técnico, en local y en la CI |
| Cuenta de Cloudflare con el dominio, y claves de Turnstile | Despliegue público | Claves de prueba oficiales de Turnstile en `.env.example` |
| Cuenta de Stripe en modo test con productos y precios | Pagos de prueba reales | `FakePaymentProvider` en desarrollo y en la CI |
| Cuenta de OpenRouter con 10 $ comprados y la privacidad configurada (6.1) | IA real | Proveedor falso determinista (6.6) |
| Servidor SMTP con SPF, DKIM y DMARC en el dominio de `MAIL_FROM` | Correo real | Mailpit en `docker-compose.yml` |
| Credenciales de Google OAuth, Google Picker y Dropbox | Acceso con Google, Drive y Dropbox | Funciones apagadas por flag |
| Repositorio remoto para restic (por ejemplo, SFTP en otro servidor) y su contraseña | Copia fuera del servidor | Copia local; el cierre operativo de F1 la exige |
| Certificado del sello de la plataforma y TSA de producción | Sello en producción | Certificado autofirmado y TSA de pruebas |
| Revisiones legales anotadas en `docs/LEGAL.md` | Activar `INVOICING_ES_ENABLED`, `HEVC_DECODE_ENABLED`, `VIDEO_H264_ENCODING_ENABLED` y las herramientas de IA en producción | Flags apagados |

Pide todas las entradas que falten en un único mensaje al empezar, y otra vez al cerrar cada fase. No las pidas una a una.

---
