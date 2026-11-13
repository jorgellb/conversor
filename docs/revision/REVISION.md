# Revisión de `super-prompt-conversor-coolify.md`

- **Fecha de la revisión y de las comprobaciones:** 31/10/2026.
- **Documentos revisados:** documento 1 (`super-prompt-conversor-coolify.md`, 1.840 líneas) y documento 2 (`pdf24-inventario-opciones.md`).
- **Entregables:** este informe, `super-prompt-conversor-coolify.v2.md` (documento completo con todos los parches aplicados) y `CHANGELOG.md` (cada cambio con su hallazgo).
- **Convenciones:** H-xx son hallazgos; P-xx, parches del apartado 8. Las citas del documento van entre comillas latinas y son literales. «Hecho» indica algo comprobado en una fuente con su URL en el apartado 3; «juicio», una valoración razonada.

---

## 1. Veredicto

No está listo para dárselo a Opus 5.5 tal cual. La arquitectura es buena (registro único de herramientas, disco con tus y `forward_auth` de Caddy, limitador atómico de IA, pruebas de efecto por opción), pero tiene dos bloqueantes: el agente no puede cerrar ninguna fase, porque los criterios exigen un despliegue y cuentas externas que no tiene y el documento no dice qué hacer sin ellos (H-01); y varios motores que procesan archivos de usuarios pueden leer archivos locales mientras todos los secretos están en el entorno de los workers (H-02). Además, el alcance real son unos 330 slugs y no unas 150 herramientas, y varios hechos han cambiado: OpenRouter permite usar modelos gratuitos sin proveedores que entrenen, OCRmyPDF 17 ya hace PDF/A sin Ghostscript, Gotenberg 8.32 trae los filtros de salida desactivados y la factura electrónica B2B tiene plazos en marcha desde el 6/10/2026. Hay también trampas de licencia concretas: `ezdxf[draw]` instala PyMuPDF, el modelo por defecto de rembg es de pago y Kokoro en español carga código GPL. Con los parches del apartado 8 (o el `v2`) sí está listo.

Tres cambios sí o sí:

1. **§0.1 y cierre en dos niveles** (H-01): entradas del propietario, dobles locales y un cierre técnico que la CI puede comprobar sola.
2. **Aislamiento del procesado** (H-02 y H-08): matriz de secretos por contenedor, motores con entorno vacío, `pandoc --sandbox`, dos Gotenberg y dos proxies de salida, y pruebas de lectura de archivos.
3. **Lista de lanzamiento y reglas de indexación** (H-18 y H-19): unas 30 herramientas para salir antes, páginas sin `noindex` solo cuando la herramienta y su contenido están listos, y cuotas por coste.

---

## 2. Tabla de hallazgos

56 hallazgos: 2 bloqueantes, 17 altos, 30 medios y 7 bajos. La corrección completa de cada uno está en los parches que se citan (apartado 8).

| ID | Gravedad | Categoría | Sección | Problema | Evidencia | Corrección propuesta | Confianza |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H-01 | Bloqueante | Ejecutabilidad | §1.3, §14, §16.1, §17, §18 | El agente no puede cerrar ninguna fase: los criterios exigen un despliegue en Coolify con healthchecks, Cloudflare, Turnstile, SMTP y un pago real en Stripe, pero el documento no dice qué accesos tiene ni qué hacer sin ellos. Tampoco qué hacer si los marcadores `{{PRODUCTO}}` llegan sin sustituir. | «el despliegue en Coolify tiene todos los healthchecks en verde»; F2: «Pago de prueba completo»; §14: «`TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` \| obligatorio»; §1.3: «`docker compose up` funciona en local solo con `.env.example`». | Nueva §0.1 con las entradas del propietario y sus dobles (claves de prueba de Turnstile, Mailpit, `FakePaymentProvider`, LLM falso). Cierre técnico comprobado en la CI y cierre operativo con token de la API de Coolify o con lista para el propietario. P-01, P-02, P-03, P-53, P-56, P-57, P-58. | Alta (juicio sobre el texto) |
| H-02 | Bloqueante | Seguridad | §7.12, §7.17, §12.1, §12.3, §12.4 | Motores que procesan entradas de usuarios pueden leer archivos locales y meterlos en el resultado, y todos los secretos están al alcance de los workers. pandoc sin `--sandbox` incrusta `![](/proc/self/environ)` en el DOCX; LaTeX lee con `\input`; SVG, EPUB y OpenSCAD pueden referenciar archivos. El documento pide limitar `include` e `import` sin decir cómo. | «markdown-a-docx, docx-a-html, html-a-docx — pandoc — F6»; «`include` e `import` limitados al directorio del trabajo»; «Secretos solo por variables de entorno generadas por Coolify». | Matriz de secretos por contenedor comprobada al arrancar; motores como subproceso con entorno vacío y proceso padre no volcable; `pandoc --sandbox`; SVG solo con `data:`; análisis previo de OpenSCAD; prueba de lectura de archivos por motor. P-30, P-33, P-46, P-48, P-56, P-58. | Alta en pandoc y en la exposición de secretos; media en el resto |
| H-03 | Alta | Licencias, ejecutabilidad | §11 | La lista permitida es inaplicable: la CI fallará con dependencias corrientes (Pillow es MIT-CMU, defusedxml PSF, libarchive-c CC0, pyassimp ISC, usd-core TOST-1.0; en npm abunda ISC y caniuse-lite es CC-BY-4.0). pip-licenses no distingue un GPL importado de uno externo, así que «GPL solo como programa externo» no se puede comprobar como está. | «**Frontend** (se distribuye al navegador): solo MIT, Apache-2.0, BSD o MPL-2.0»; «hace fallar la CI si aparece una licencia prohibida». | `scripts/license_policy.yaml` con listas explícitas; la CI falla con licencias desconocidas y con cualquier paquete Python o npm GPL o AGPL; GPL solo como binarios de §2. P-04, P-45. | Alta (PyPI consultado hoy) |
| H-04 | Alta | Licencias | §2, §6.4, §7.3, §7.11, §7.16, §7.19, §14 | Trampas no señaladas en las que un agente cae al seguir la documentación de cada proyecto: `ezdxf[draw]` instala PyMuPDF (AGPL) y es el backend de PDF de ezdxf; el modelo por defecto de rembg es `bria-rmbg`, de pago para uso comercial; Kokoro en español usa espeak-ng a través de `phonemizer-fork` (GPL-3.0+) dentro del proceso; extract-msg, el parser habitual de MSG, es GPL; xmlsig se declara AGPL; el paquete `ocrmypdf` de las distribuciones arrastra Ghostscript; draw.io desktop es GPL-3.0 y no está en la lista de GPL externos. | «dxf-a-pdf — ezdxf — F2»; «quitar-fondo — rembg con un modelo cuya licencia permita uso comercial»; «Kokoro (voz, Apache-2.0)»; «eml-a-pdf, msg-a-pdf — parser de correo y Chromium». | Motores concretos en §2, §6.4, §7.3, §7.11 y §7.19; lista de trampas en §11; `check_images.sh` falla si hay `gs`, `mutool` o PyMuPDF en una imagen. P-04, P-19, P-24, P-29, P-33, P-34, P-45. | Alta (PyPI, npm y README consultados hoy) |
| H-05 | Alta | IA, RGPD | §6.1, §6.6 | El documento da por hecho que los modelos gratuitos exigen permitir que el proveedor entrene con los datos. Ya no es así: OpenRouter separa los ajustes de modelos gratuitos y de pago, deja de enrutar a proveedores que entrenan si se desactiva, y `provider.data_collection: "deny"` lo impone por petición. A 5/10/2026, 9 de 19 modelos gratuitos estaban en proveedores que pueden entrenar. El diseño actual envía documentos con datos personales a esos proveedores sin necesidad. | «Para usar modelos gratuitos hay que permitir en la configuración de privacidad que los proveedores registren o entrenen con los textos». | Cuenta sin proveedores que entrenan ni publican; `data_collection: "deny"` en todas las peticiones; aviso fiel; `AI_UNAVAILABLE` si no queda modelo válido; EIPD. P-16, P-17, P-21, P-56, P-58. | Alta en el mecanismo; media en el recuento (fuente secundaria) |
| H-06 | Alta | IA, producto | §6.3, §9.3 | Los planes no caben en el presupuesto: 60 peticiones diarias por usuario Pro contra una reserva Pro de 400 se agotan con 7 usuarios Pro activos; 18 peticiones por minuto compartidas dan para unas 9 conversaciones de chat a la vez; traducir 300 páginas son 30 a 45 peticiones. El troceo fijo ignora el máximo de tokens de salida de cada modelo, y la documentación no aclara si los intentos fallidos cuentan. | «Peticiones de IA al día \| 0 \| 5 \| 60»; «Páginas por tarea de IA \| — \| 30 \| 300»; «`AI_PRO_RESERVE` \| 400»; «1 por cada ~20.000 caracteres». | Límites de 0, 3 y 30 al día; máximo de 20 por tarea; 150 páginas en Pro; bloques según `max_completion_tokens`; reconciliación con `free_model_daily_requests` de `/key`; IA anunciada como beta. P-16, P-17, P-18, P-27, P-42, P-54. | Alta en la aritmética; media en los supuestos (ver nota de cálculo) |
| H-07 | Alta | Seguridad, infraestructura | §3.1, §13.1 | UFW no filtra los puertos que publica Docker (lo dice la documentación de Coolify): el panel (8000) y los puertos 6001 y 6002 quedan expuestos aunque el cortafuegos «solo abra 22, 80 y 443». Con 80 y 443 abiertos a todo internet, se puede saltar el WAF atacando la IP del servidor y falsificar `CF-Connecting-IP`. | «cortafuegos que solo abra 22, 80 y 443. El panel de Coolify (8000) solo desde la IP del administrador o a través de Cloudflare Access». | Cortafuegos del proveedor o cadena `DOCKER-USER`; 80 y 443 solo desde los rangos de Cloudflare, con certificado de origen; cerrar 8000, 6001 y 6002; IP real solo desde Cloudflare. P-05, P-49, P-51. | Alta (documentación de Coolify) |
| H-08 | Alta | Seguridad, redes | §4.6, §7.3, §7.17, §7.23, §12.2 | El mapa de redes no funciona: `apiint` no puede enviar la copia con restic porque está en la red sin salida; `api` y `web` necesitan salir a Turnstile, Stripe, SMTP y Google; Smokescreen identifica clientes por certificado TLS, así que una sola instancia no puede aplicar una política a `workerai` y otra a la captura web; y un único Gotenberg con salida renderiza también el HTML que suben los usuarios. Desde la 8.32, los filtros de salida de Gotenberg vienen desactivados y `downloadFrom` y los webhooks siguen disponibles. | «Red interna (`internal: true`) sin salida a internet para workers, gotenberg, valkey, postgres, apiint, upload y files»; «cualquier destino fuera de una lista permitida para `workerai`»; §4.6: «envía la copia con restic». | Redes `internal`, `edge`, `webrender` y `airelay`; dos Smokescreen (`egressai` con lista y `egressweb` para IP públicas); `gotenberg` sin salida y con los flags de denegación, y `gotenbergweb` solo para URL; `downloadFrom` y webhooks bloqueados; prueba de humo de salida. P-04, P-06, P-24, P-33, P-38, P-47, P-54, P-58, P-59, P-77. | Alta (README de Smokescreen y notas de Gotenberg) |
| H-09 | Alta | Seguridad, legal (firma) | §10, A.6 | La clave del sello vive en el mismo VPS que los parsers, sin aislamiento, límites ni registro de uso, y no hay variable para el PIN. A.6 ofrece un sello «de la empresa» en servidor, en contradicción con §7.24, que deja fuera los certificados con clave privada. Un sello en un token software no puede ser cualificado. | «Certificado de la plataforma por PKCS#11»; A.6: «certificado [sello de la plataforma o de la empresa], en servidor por PKCS#11»; §14: «`SIGN_PKCS11_MODULE`, `SIGN_CERT_PATH`, `TSA_URL`». | Solo `workersign` monta el token y conoce el PIN; `seal_signatures`, `SEAL_DAILY_LIMIT` y `SEAL_ENABLED`; certificado de empresa solo por firma interrumpida; no anunciar «cualificado»; TSA de producción como entrada del propietario. P-43, P-44, P-54, P-72. | Alta en el diseño; media en lo legal (consultar) |
| H-10 | Alta | Seguridad, licencias (facturas) | §7.14, §7.23, A.2 | La firma XAdES de Facturae «con el certificado de la empresa» no tiene motor y, como está, implica subir la clave privada al servidor. El paquete que suele usarse en Python, xmlsig, se declara AGPL en PyPI. La verificación de .xsig tampoco tiene motor XAdES. | «Facturae puede llevar firma XAdES opcional con el certificado de la empresa»; «verificar-firma — pyhanko-certvalidator». | Firma XAdES-EPES en el navegador con xadesjs (MIT) y PKI.js (BSD-3-Clause); verificación con signxml (Apache-2.0); pyHanko para CAdES y PAdES. P-04, P-32, P-37, P-38, P-64, P-72. | Alta (npm y PyPI consultados hoy) |
| H-11 | Alta | Legal (facturación) | §7.23 | El aviso legal se queda corto: no recoge las fechas de Veri*factu tras el RDL 15/2025 (productores desde el 29/7/2025; usuarios el 1/1/2027 y el 1/7/2027) ni la factura electrónica B2B (RD 238/2026 y Orden HAC/1028/2026, en vigor desde el 6/10/2026, con copia en UBL a la solución pública). pdf-a-factura-electronica, que también genera facturas, queda sin flag. | «Deja crear-factura y crear-factura-electronica detrás de su flag hasta la revisión con un asesor»; «(Reglamento Veri*factu, RD 1007/2023)». | Flag común `INVOICING_ES_ENABLED` para los tres generadores; validar y visualizar pueden ir antes; aviso con las normas vigentes; salida UBL 2.1. P-37, P-64. | Alta en normas y fechas; duda razonable en la calificación de cada herramienta (asesor fiscal) |
| H-12 | Alta | Seguridad, paridad | §7.1, A.6, §16.6 | El método por defecto de redactar-pdf («eliminar el contenido bajo el área» con EmbedPDF) es menos seguro que el de PDF24, que rasteriza, y la documentación de EmbedPDF no explica qué hace con imágenes y trazados. La prueba solo mira el texto: una imagen tapada podría conservar sus píxeles. | A.6: «[Eliminar el contenido bajo el área], con EmbedPDF y PDFium»; §16.6: «redactar-pdf: tras redactar, el texto ya no se encuentra en el resultado»; documento 2: «Al guardar se rasterizan las páginas afectadas; es irreversible». | Por defecto, rasterizar las páginas afectadas a 300 ppp; el método fino solo si pasa pruebas con texto, imagen y vector. P-22, P-56, P-73. | Media (no verificable qué elimina EmbedPDF) |
| H-13 | Alta | Fiabilidad, abuso | §4.2 | En tusd, `post-finish` no es bloqueante: el cliente puede llamar a `POST /v1/jobs` antes de que exista la fila en `uploads` (fallos intermitentes). Con `Upload-Defer-Length`, el tamaño no se conoce en `pre-create`, así que un anónimo puede subir hasta el máximo de Pro. | «Gancho `post-finish`:»; «Comprueba el tamaño contra el plan». | Validación en `pre-finish` (bloqueante), rechazo de `SizeIsDeferred`, estados `ready` y `rejected`, reserva de disco. P-08, P-56. | Alta (documentación de tusd) |
| H-14 | Alta | Fiabilidad | §5.3 | Con Valkey como broker y `acks_late`, Celery reentrega las tareas sin confirmar al vencer el `visibility_timeout` (una hora por defecto): una transcripción de 4 h o un vídeo de 1 h se ejecutarían dos veces. Un contenedor muerto por memoria reencola su tarea sin límite. Las contraseñas de PDF viajarían en claro en los argumentos de Celery, que Valkey puede guardar en disco. | «`acks_late` y `prefetch_multiplier=1`»; «Duración de audio \| 10 min \| 30 min \| 4 h»; «Contraseñas de PDF solo en memoria». | `visibility_timeout` mayor que el `time_limit` máximo; latidos e intentos en `jobs` con `WORKER_LOST`; prioridades configuradas; sin backend de resultados; parada en caliente; secretos cifrados con `JOB_SECRETS_KEY`. P-14, P-54, P-56. | Alta (comportamiento conocido de Celery con Redis y Valkey) |
| H-15 | Alta | Viabilidad | §3.1, §5.4, §12.1 | Con la concurrencia de 5.4 hay 23 procesos en 8 vCPU, y OCRmyPDF, FFmpeg, torch y faster-whisper usan por defecto todos los núcleos. La suma de los picos de memoria del catálogo completo ronda 50 GB, por encima de los 32 GB propuestos (apartado 4). Kokoro, que gasta CPU, comparte grupo con trabajos que solo esperan a la red. | «8 vCPU, 32 GB de RAM y 300 GB o más de NVMe»; 5.4: «`pdf` \| pikepdf, qpdf, pypdfium2, Pillow \| 4». | Concurrencia por tamaño de VPS; hilos fijados por motor; `mem_limit`, `memswap_limit` y `oom_score_adj`; colas `light` y `heavy`; 16 vCPU y 64 GB para el catálogo completo. P-05, P-15, P-27, P-46. | Media (estimaciones a medir con k6) |
| H-16 | Alta | Operación | §4.6, §13.2 | La copia fuera del servidor es opcional: perder el VPS es perder la base de datos. No se copian los secretos de Coolify (sin `AUTH_SECRET` no se descifran las claves JWKS que Better Auth guarda cifradas), ni el token del sello, ni la base de datos de Coolify. `pg_dump` falla si el cliente de `apiint` no es de la misma versión mayor que el servidor, y las tareas programadas de Coolify cortan a los 300 s por defecto. | «**Copia fuera del servidor (opcional pero muy recomendada)**»; «cada día a las 03:15, en el contenedor `apiint`». | Copia cada 6 horas; restic remoto obligatorio para el cierre operativo de F1; copia cifrada de variables, `.env` y base de datos de Coolify y token del sello; cliente de PGDG; 3.600 s; simulacro trimestral y prueba en la CI. P-11, P-52, P-56, P-58. | Alta |
| H-17 | Alta | Ejecutabilidad, alcance | §5.1 | La regla de que toda herramienta de navegador «ofrece la ruta de servidor» por encima de 100 MB obliga a duplicar en servidor decenas de herramientas que no tienen motor de servidor (editar, anotar, folleto, collage, generar-contrasena). El agente lo hará todo o decidirá por su cuenta. | «Si el archivo supera 100 MB o el dispositivo falla por memoria, la herramienta ofrece la ruta de servidor.» | Solo las herramientas marcadas `hybrid`, con lista cerrada, tienen parte de servidor; el resto avisa. P-12, P-13. | Alta |
| H-18 | Alta | Producto, SEO, alcance | §0, §7, §8.2, §17 | El catálogo tiene unos 330 slugs (unas 660 páginas en dos idiomas), no unas 150 herramientas, y F1 ya reúne unas 45 herramientas más toda la infraestructura. Con plantillas y contenido escrito en serie, el riesgo de contenido escaso o duplicado es alto, y no hay reglas para las páginas de herramientas apagadas ni para los alias. No hay lista de lanzamiento. | «Cada herramienta tiene página en `/es/<slug-es>` y `/en/<slug-en>` desde su fase»; «Las combinaciones sin página propia llevan `noindex`»; «pub-a-pdf — alias de publisher-a-pdf — F2». | Reglas de indexación (solo herramienta activa, probada y con contenido), contenido mínimo comprobado en la CI, `canonical` en alias, lista de lanzamiento y orden de fases. P-13, P-36, P-39, P-40, P-57. | Alta en el recuento (script sobre el documento); media en el impacto SEO |
| H-19 | Alta | Producto | §9.3 | Las cuotas anónimas (3 tareas de servidor al día para cualquier herramienta) no compiten con PDF24, gratis y sin límite, y comprimir-pdf, una de las búsquedas más frecuentes, es de servidor. Tratar igual una compresión de segundos y un OCR de minutos penaliza lo barato. | «Tareas de servidor al día \| 3 \| 10 \| 500 (uso justo)»; «comprimir-pdf — pikepdf y Pillow». | Cuotas por clase de coste (`light`: 20, 50 y 1.000; `heavy`: 2, 10 y 200), archivos y tamaño por tarea y definición de tarea. P-13, P-42, P-57. | Media (juicio de producto) |
| H-20 | Media | Ejecutabilidad | §7.4, A.1, A.9 | Gotenberg solo produce PDF, pero varias herramientas necesitan LibreOffice para otros formatos (pdf-a-odt, pdf-a-ods, pdf-a-odp, pdf-a-rtf, abrir ODT en escribir-pdf, modo «Fiel al diseño»), y el documento no dice dónde corre. | «pdf-a-odt, pdf-a-ods, pdf-a-odp, pdf-a-rtf — salida anterior convertida con LibreOffice»; «con la importación de PDF de LibreOffice». | LibreOffice con unoserver (MIT) en `workeroffice`. P-04, P-25, P-31, P-60, P-75. | Alta (documentación de Gotenberg) |
| H-21 | Media | Producto, calidad | §7.4, A.9 | Docling extrae estructura; el DOCX reconstruido con python-docx es editable pero no fiel al diseño, que es lo que espera quien busca «PDF a Word». En CPU, un documento de 225 páginas necesitó unos 2,5 GB con el backend pypdfium y 6,2 GB con el nativo. | «pdf-a-word, pdf-a-excel, pdf-a-ppt — Docling con python-docx, openpyxl y python-pptx». | Backend pypdfium2, aviso de expectativas, modo fiel con LibreOffice, límites de páginas y tiempo. P-25. | Media |
| H-22 | Media | Legal, códecs | §7.2, §7.9, §7.11, §11, §14 | HEIC queda apagado por el riesgo de patentes HEVC, pero el vídeo H.265 se decodifica sin flag; el pool HEVC Advance cobra por usuario a servicios en la nube que usan decodificadores HEVC. La codificación H.264 está en `true` pese a la misma advertencia. AAC no está «sin restricciones». Muchas conversiones de vídeo no necesitan recodificar. | «Todo lo HEIC va detrás de `HEIC_ENABLED`»; «H.265 solo para decodificar»; «`VIDEO_H264_ENCODING_ENABLED` \| `true`»; «sin restricciones: MP3, AAC». | Un flag `HEVC_DECODE_ENABLED` para HEIC y vídeo; H.264 apagado hasta la revisión; remultiplexar con `-c copy` primero. P-23, P-28, P-29, P-45, P-54, P-78, P-79. | Media (los términos del pool son públicos; su aplicación a HEIC es duda razonable: abogado de patentes) |
| H-23 | Media | Coherencia | §9.3, §14 | Los límites de audio y vídeo están duplicados en `plans` y en variables de entorno, y no coinciden: la variable de Pro es de 4 horas para «audio y vídeo» y el plan dice vídeo hasta 1 hora. | «`AV_MAX_DURATION_PRO_SECONDS` \| `14400` \| Audio y vídeo Pro»; «Vídeo \| No \| No \| Sí, hasta 1 h y 1 GB». | Límites solo en `plans`, sembrada desde `config/plans.yaml`; se eliminan `AV_MAX_DURATION_*` y `MESH_MAX_TRIANGLES_*`. P-42, P-54. | Alta |
| H-24 | Media | Coherencia, hechos | §2, §7.5, A.5 | El stack instala 9 idiomas de Tesseract y el Anexo promete unos 125. OCRmyPDF 17 ya hace PDF/A sin Ghostscript (`--pdfa-backend internal`), pero algunos archivos solo se convierten con Ghostscript y el documento no dice qué hacer entonces. En la v17, `--skip-text` es un alias de `--mode skip`, y `--remove-background` aparece retirado en notas antiguas y documentado en la guía actual. | «Tesseract (spa, cat, eus, glg, eng, fra, deu, ita, por)»; «Lista completa de Tesseract (unos 125)»; «por la ruta sin Ghostscript». | `tessdata_fast` para todos y `tessdata_best` para los 9; `--pdfa-backend internal` con error claro y alternativa rasterizada; opciones de la v17. P-04, P-70, P-71. | Alta (documentación de OCRmyPDF) |
| H-25 | Media | Hechos | §6.4, §14 | El modelo de embeddings por defecto no está en la lista de modelos que admite fastembed. | «por ejemplo `intfloat/multilingual-e5-small`; verifícalo»; «`EMBEDDINGS_MODEL` \| `intfloat/multilingual-e5-small`». | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (Apache-2.0, 384 dimensiones). P-04, P-19, P-54. | Alta |
| H-26 | Media | Ejecutabilidad | §3.2, §9.4, §13.2 | Faltan tablas que el documento usa (eventos de Stripe, consentimientos de IA, usos del sello, contador de correos) y columnas de `signature_requests`, `signers` y `audit_events`. `profiles.role` duplica el `role` del plugin de administración de Better Auth. No se dice quién crea las tablas de Better Auth frente a Alembic. El índice único de `idempotency_key` choca con trabajos caducados. | «`signature_requests`, `signers`, `audit_events` \| flujo de firmas (F4)»; «`profiles` \| `user_id`, `plan_id`, `role`»; «`idempotency_key` (único)». | Tabla completa en 9.4, servicio `migrateauth` e índice parcial. P-06, P-43, P-52. | Alta |
| H-27 | Media | Ejecutabilidad | §14 | Faltan variables que el diseño necesita (PIN y etiquetas PKCS#11, URL de Better Auth, flags de Drive y Dropbox, guardas de colas, límites de píxeles, proxies separados) y sobran las duplicadas con `plans`. | «`SIGN_PKCS11_MODULE`, `SIGN_CERT_PATH`, `TSA_URL` \| vacío en desarrollo»; «`GOOGLE_PICKER_CLIENT_ID`, `GOOGLE_PICKER_API_KEY`, `DROPBOX_APP_KEY` \| vacío (desactivado)». | Tabla de §14 revisada. P-54. | Alta |
| H-28 | Media | Ejecutabilidad | §5.2, §14 | Hay tres mecanismos de flags (variable por herramienta, fila en `feature_flags` y flags temáticos como `HEIC_ENABLED`) sin precedencia definida. | «`flag` \| `TOOL_<SLUG>_ENABLED` y fila en `feature_flags`»; «`HEIC_ENABLED` \| `false`». | Precedencia explícita: la variable a `false` apaga siempre, después manda la base de datos y los temáticos solo apagan. P-13, P-55. | Alta |
| H-29 | Media | Arquitectura | §9.1, §12.2 | El chat en streaming está en la API pública, pero solo `workerai` sale a OpenRouter. | «`POST /v1/ai/chat` \| Mensaje de chat en streaming»; «Solo `workerai` (hacia OpenRouter) y las conversiones desde URL». | La API encola en `workerai` y retransmite por SSE lo que este publica en Valkey. P-41. | Alta |
| H-30 | Media | Capacidad | §4.5, §5.3 | No hay control de admisión: en un pico, las colas crecen sin límite y los anónimos esperan indefinidamente. La guarda de disco mira el espacio libre, pero no reserva el que ocuparán la entrada, el temporal y la salida de las subidas en curso. | «Comprueba el espacio libre en disco (sección 4.5)». | Reserva de disco por tres, guarda de colas con `QUEUE_FULL`, espera visible y caché de HTML en Cloudflare. P-10, P-15, P-51, P-54. | Media |
| H-31 | Media | Abuso | §5.1, §9.3, §12.4 | «Tarea» no está definida (¿un lote de 50 archivos es una?), no hay límite de archivos ni de tamaño total por tarea, los tokens anónimos se emiten sin límite resolviendo Turnstile, y no se dice que `CF-Connecting-IP` solo vale si llega desde Cloudflare. | «Tareas de servidor al día \| 3»; «Rate limiting en API y tusd por IP y por usuario». | Definición de tarea, archivos y tamaño por tarea, `ANON_TOKENS_PER_IP_DAY`, cuotas por token y por IP (/64) e IP de confianza solo desde Cloudflare. P-08, P-12, P-41, P-42, P-49, P-54. | Alta |
| H-32 | Media | Seguridad web | §4.4, §9.1, §12.4 | No hay CSP, HSTS ni `Permissions-Policy` en una web que abrirá certificados .p12 en firmar-pdf. `files` sirve contenido de usuarios sin `CSP: sandbox`. La cookie httpOnly del token anónimo abre la puerta a CSRF si la API acepta cookies. | §4.4: «envía `Content-Disposition: attachment`, `Cache-Control: private, no-store` y `X-Content-Type-Options: nosniff`»; §9.1: «(cookie httpOnly y token para tus)». | Cabeceras completas, `CSP: sandbox` en `files` y API solo con `Authorization`. P-09, P-12, P-49. | Alta |
| H-33 | Media | Abuso | §8.2 | El envío por correo a cualquier destinatario desde cuentas gratuitas, que solo cuestan un correo, sirve para spam y phishing con el dominio del producto. | «**Enviar por correo**, solo para usuarios registrados»; «límite diario `MAIL_SHARE_DAILY_LIMIT` y Turnstile». | Gratuito: solo a su propia dirección; Pro: hasta 3 destinatarios; enlace de abuso; SPF, DKIM y DMARC. P-40. | Media |
| H-34 | Media | Privacidad | §6.5, §9.4 | Las cachés de texto, fragmentos y resultados de IA van por sha256 sin propietario: si dos personas suben el mismo documento, la segunda recibe al instante el resultado de la primera, lo que revela que alguien lo procesó. | «Caché por `(sha256, herramienta, opciones, idioma)`»; «`document_texts` \| `sha256`, `pages` (jsonb)». | Propietario en todas las claves; ninguna caché compartida. P-20, P-43, P-56. | Alta |
| H-35 | Media | Seguridad | §5.3, §12.3 | Las contraseñas de proteger y desbloquear acabarían en los argumentos de Celery (que Valkey puede persistir) y en la clave de idempotencia, que incluye las opciones. | «Contraseñas de PDF solo en memoria»; «**Idempotencia** por `(propietario, sha256 de entradas, herramienta, opciones)`». | Cifrado con `JOB_SECRETS_KEY`; opciones sin secretos en la clave y en `jobs.options`; argumentos de tareas fuera de los logs. P-14, P-49, P-54. | Alta |
| H-36 | Media | Operación, coste | §3.3 | Publicar las imágenes expone el código cerrado y distribuye programas GPL, con la obligación de ofrecer su código fuente. Construir unas 13 imágenes pesadas por cambio gasta pronto los 2.000 minutos mensuales de Actions de un repositorio privado. | «Documenta cómo dar acceso al registro privado o publicar las imágenes como públicas.» | Imágenes siempre privadas, token de solo lectura, filtros por ruta y caché, y el coste como decisión del propietario. P-07. | Alta en la exposición; media en el coste |
| H-37 | Media | Legal, CDN | §0 (decisión 7), §4.4 | Las condiciones del CDN de Cloudflare en Free, Pro y Business no permiten servir vídeo ni una proporción desproporcionada de archivos grandes, y `files` sirve por el proxy vídeos de hasta 1 GB. | «Delante de todo, Cloudflare»; «Vídeo \| No \| No \| Sí, hasta 1 h y 1 GB». | Medir el volumen servido por tipo de archivo y tener preparado el plan B del apartado 5. P-09. | Media (el umbral no es público) |
| H-38 | Media | Paridad | §7.3, §7.5, A.1 | Falta convertir-a-pdf, la página general de PDF24; web-a-pdf no admite URL de documentos convertibles, que PDF24 sí admite; no está claro si eliminar-metadatos-pdf tiene página propia. | Documento 2: «**convertir-a-pdf** (S): página general»; «URL de la página o de cualquier documento enlazado convertible»; documento 1: «metadatos-pdf (ver, editar y quitar)». | convertir-a-pdf en F1; descarga y conversión de documentos enlazados por `egressweb`; eliminar-metadatos-pdf con página propia. P-24, P-26, P-59. | Alta |
| H-39 | Media | Paridad (privacidad), coste | §7.5, §7.11, §7.17, §7.20 | PDF24 compara PDF y convierte SVG en el navegador; aquí van a servidor, igual que mermaid (otro Chromium con mermaid-cli) y las miniaturas 3D (Chromium sin interfaz con WebGL). En el navegador es más privado, más barato y más sencillo. | «comparar-pdf — diferencias de texto y diferencias visuales por página — F2»; «svg-a-jpg — resvg — F5»; «mermaid-a-png, mermaid-a-svg — mermaid-cli — F6». | comparar-pdf híbrida; SVG con `@resvg/resvg-wasm`; mermaid, glTF Transform y three.js en el navegador; mermaid-cli y resvg salen del servidor. P-04, P-26, P-29, P-33, P-35, P-74, P-76. | Alta en los hechos de PDF24 (documento 2) |
| H-40 | Media | Calidad, paridad | A.5 | «Reducir fuentes incrustadas (subconjunto)» activo por defecto sin Ghostscript obliga a reescribir fuentes de PDF arbitrarios, con riesgo de romper el texto. PDF24 tiene cuatro casillas de borrado separadas y aquí son una. | «Reducir fuentes incrustadas (subconjunto y duplicadas) [sí]»; «Quitar adjuntos, anotaciones, marcadores y metadatos [no]». | Reducción segura y cuatro casillas. P-67, P-68. | Media |
| H-41 | Media | Implementación | §7.5, A.5, §16.6 | Pasar a gris reescribiendo operadores falla con sombreados por función y espacios DeviceN, y la prueba exige que no quede ningún color en todo el documento, así que el agente puede atascarse. | «no queda ningún operador de color distinto de gris, y el texto sigue siendo extraíble». | Rasterizar en gris solo las páginas no convertibles, avisando, y prueba ajustada. P-26, P-56, P-69. | Media |
| H-42 | Media | Ejecutabilidad | A.1 | La vista previa con «el salto real de página» y el índice con números reales necesitan paginación: la extensión Pages de TipTap es de pago y pagedjs lleva años sin versión nueva. | «**Vista previa por páginas** con el salto real de página»; documento 2: «índice con números de página reales». | Vista previa exacta generada en servidor e índice en dos pasadas con `generateDocumentOutline`. P-60. | Media |
| H-43 | Media | Hechos (facturación) | §7.23, A.2 | KoSIT no trae escenarios oficiales de EN 16931 sin CIUS ni de Factur-X: solo hay configuraciones públicas de XRechnung y Peppol BIS. KoSIT 1.6 solo recibe mantenimiento. | «con los escenarios oficiales de EN 16931, XRechnung, Peppol BIS y Factur-X». | Configuraciones públicas donde existen y escenarios propios con los artefactos oficiales en el resto. P-37, P-65. | Alta (README de KoSIT) |
| H-44 | Media | Ejecutabilidad | §1.8 | Exigir muestras «con licencia compatible» para PST, MSG, DWG, bgcode o .gcode.3mf es a menudo imposible: el agente se atascará o se las inventará. | «Usa muestras con licencia compatible y anota su origen en `tests/fixtures/SOURCES.md`». | Generarlas con cualquier herramienta (no se distribuyen), descargarlas solo si se pueden guardar en el repositorio privado, o desactivar la herramienta. P-03. | Alta |
| H-45 | Media | Ejecutabilidad | §1.7, §17 | «Calidad suficiente» no está definida y choca con «Ninguna fase se cierra con herramientas por debajo de esas opciones». | «Si una herramienta no alcanza calidad suficiente, déjala desactivada con su flag». | Lista si pasa 16.5 y 16.6 y tiene contenido; como mucho, el 10 % de las herramientas de una fase desactivadas y ninguna de la lista de lanzamiento. P-03, P-57. | Alta |
| H-46 | Media | Arquitectura | §5.2 | No se dice cómo llega el registro de Python a la web en TypeScript ni se impide que la API importe los motores (torch, OpenCascade) al cargar el registro, lo que dispararía su memoria y el tamaño de su imagen. | «Cada herramienta es un módulo Python (y, si es de cliente, un módulo TypeScript)». | Separación `spec.py` e `impl.py`, `registry.json` exportado, tipos generados y prueba de importación. P-13, P-55. | Alta |
| H-47 | Media | RGPD | §6.6, §9.1, §12.5 | Faltan bases jurídicas, registro de actividades, EIPD del uso de IA y plazos de `anon_clients` y logs; en los subencargados faltan Sentry, Google y Dropbox y las garantías de transferencia. El aviso de IA no menciona la transferencia ni la conservación. | «Lista de subencargados: proveedor del VPS, Cloudflare, OpenRouter y sus proveedores de modelos, Stripe y proveedor de correo». | §12.5 completa, `ai_consents` y exportación de datos. P-21, P-41, P-50. | Media (no es asesoramiento jurídico) |
| H-48 | Media | Negocio | §0 (decisión 6), §13.3, §14 | Con Stripe en modo test no hay ingresos, el precio de Pro no está definido y no hay pasos para pasar a producción (IVA en ventanilla única, registros de Stripe Tax, términos). | «Pagos con Stripe en modo test»; «`STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_PRO_YEARLY` \| modo test». | Paso 11 de §13.3 y decisión del apartado 5. P-53. | Alta |
| H-56 | Media | Organización | Todo el documento | Con unos 105 KB y 1.840 líneas, el agente lo tendrá entero al empezar, pero tras compactar el contexto perderá detalles del Anexo A (630 líneas) justo cuando los necesite. | Tamaño del documento. | Primer paso: trocearlo en `docs/spec/` y releer lo de cada fase. P-03, P-55. | Media |
| H-49 | Baja | Despliegue | §13.2 | `migrate` es de un solo uso: quien depende de ella debe esperar `service_completed_successfully`, no `service_healthy`, y conviene `restart: "no"`. Los despliegues de Compose recrean todos los contenedores. | «`exclude_from_hc: true` en `migrate` y `depends_on` con `condition: service_healthy`». | P-52. | Media |
| H-50 | Baja | Hechos (Coolify) | §13.2 | `SERVICE_FQDN_*` sigue existiendo pero hoy es el dominio sin esquema; `SERVICE_URL_*` lleva el esquema. Coolify convierte guiones y puntos en guiones bajos. | «`SERVICE_FQDN_WEB_3000`». | Usar `SERVICE_URL_*` para las URL públicas. P-52. | Alta |
| H-51 | Baja | SEO | §8.2 | Google retiró en 2026 los resultados enriquecidos de FAQ, y `SoftwareApplication` necesita `offers` y valoraciones para mostrarse. | «Datos estructurados `SoftwareApplication` y `FAQPage`». | P-40. | Media (fuentes secundarias de mayo de 2026) |
| H-52 | Baja | Paridad, coherencia | §7.1, §7.23, A.1 | PayPal en PDF24 acepta correo o ID y aquí solo paypal.me; faltan valores por defecto de colores y borde del QR; slug `rellenar-formularios-pdf` frente a `rellenar-pdf` del Anexo; alias sin `canonical`; el RD 1553/2005 del DNI está derogado por el RD 255/2025. | «PayPal: enlace paypal.me con importe y moneda»; «rellenar-formularios-pdf»; «26 × 32 mm (DNI y pasaporte españoles)». | P-22, P-39, P-61, P-62, P-63. | Alta |
| H-53 | Baja | 3D | §7.20 | comprimir-glb no tiene motor y render-modelo-3d depende de WebGL en un Chromium sin interfaz. | «comprimir-glb (Draco) y render-modelo-3d (miniatura PNG con three.js en Chromium sin interfaz)». | Los dos en el navegador con glTF Transform, draco3d y three.js. P-35. | Media |
| H-54 | Baja | Integraciones | §8.2 | El Saver de Dropbox no sube desde el navegador: los servidores de Dropbox descargan la URL. Cargar los scripts de Google y Dropbox al abrir la página añadiría cookies de terceros. | «el navegador sube el resultado directamente, sin pasar credenciales por el servidor». | P-40. | Media |
| H-55 | Baja | UX | A.4 | Imprimir un PDF desde un iframe falla en Safari y en la mayoría de navegadores móviles. | «lo imprime desde un iframe». | Ofrecer la descarga del PDF de impresión. P-66. | Media |

### Nota de cálculo: consumo de IA (pasada 6)

Supuestos explícitos (juicio, a contrastar con datos reales en F3): un usuario gratuito que usa IA hace 3 peticiones al día; un Pro, 15; el reparto es 50 % chat, 20 % resúmenes, 20 % traducciones y 10 % resto.

| Escenario | Gratuitos con IA | Pro con IA | Peticiones al día | Resultado con el diseño original (5 y 60) |
| --- | --- | --- | --- | --- |
| Arranque | 100 | 10 | 100 × 3 + 10 × 15 = 450 | Cabe (47 % de 950) |
| Crecimiento | 300 | 30 | 900 + 450 = 1.350 | Los gratuitos agotan sus 550 peticiones hacia mediodía UTC; los Pro superan su reserva de 400 por la tarde |
| Pro al máximo | — | 7 | 7 × 60 = 420 | La reserva Pro de 400 se agota con 7 usuarios |

- **Por minuto:** con 18 peticiones por minuto y conversaciones de un mensaje por minuto, caben unas 18 a la vez; con la mitad reservada al chat (`AI_CHAT_RPM_SHARE`), unas 9. Cada respuesta de un modelo gratuito tarda entre 5 y 60 s (estimación), así que la cola se nota con poca gente.
- **Traducción:** 300 páginas son unos 600.000 a 900.000 caracteres. Con bloques de unos 20.000 caracteres, salen 30 a 45 peticiones para una sola tarea, casi el cupo diario de un Pro del diseño original. Con salidas máximas de 8.000 tokens, los bloques útiles son más pequeños y salen más peticiones.
- **Conclusión:** con 1.000 peticiones diarias, la IA es un gancho de captación y una ventaja menor de Pro, no la base del plan de pago. Los parches dejan 3 y 30 peticiones al día, 20 por tarea, 150 páginas en Pro y la etiqueta «beta, sujeta a disponibilidad».

---

## 3. Registro de verificación

Consultado el 31/10/2026. «Sin fecha» indica que la página no muestra fecha; en ese caso se toma como fecha la de consulta.

| # | Afirmación | Resultado | Fuente | Fecha de la fuente |
| --- | --- | --- | --- | --- |
| 1 | Coolify v4: variables `SERVICE_FQDN_*`, `SERVICE_PASSWORD_*`, `SERVICE_PASSWORD_64_*` y `SERVICE_USER_*` | Correcta con matiz: existen; `SERVICE_URL_<ID>` lleva esquema y `SERVICE_FQDN_<ID>` es solo el dominio; el sufijo numérico es el puerto; guiones y puntos pasan a guion bajo | https://coolify.io/docs/knowledge-base/docker/compose | Sin fecha |
| 2 | `exclude_from_hc` para servicios de un solo uso | Correcta | https://coolify.io/docs/knowledge-base/docker/compose | Sin fecha |
| 3 | Build pack Docker Compose desde Git; healthchecks definidos en el Compose | Correcta | https://coolify.io/docs/knowledge-base/docker/compose | Sin fecha |
| 4 | gVisor (`runtime: runsc`) conservado por Coolify | No verificable: no hay documentación; hay que probarlo en el despliegue | https://coolify.io/docs/core/docker-and-containers ; https://gvisor.dev/docs/user_guide/quick_start/docker/ | Sin fecha |
| 5 | «Coolify v4» como versión estable | Correcta: v4.0.0 estable desde abril de 2026 y 4.3.x en septiembre, según fuentes secundarias; no confirmado en la página oficial de versiones | https://wz-it.com/blog/coolify-v4-0-0-self-hosted-paas-heroku-alternative/ ; https://www.bitdoze.com/es/resena-coolify-v5-paas-autoalojado/ | 2026 |
| 6 | El cortafuegos «solo abra 22, 80 y 443» protege el panel | Incorrecta: las reglas NAT de Docker se saltan UFW; Coolify recomienda el cortafuegos del proveedor y cerrar 8000, 6001 y 6002 | https://coolify.io/docs/core/infrastructure/servers/firewall | Sin fecha |
| 7 | Tareas programadas de Coolify en un contenedor del Compose | Correcta: se indica el nombre del servicio; tiempo máximo entre 60 y 36.000 s, 300 por defecto | https://coolify.io/docs/core/automation/scheduled-tasks/overview | Sin fecha |
| 8 | OpenRouter `:free`: 20 por minuto; 1.000 al día con 10 créditos comprados | Correcta (50 al día sin ellos) | https://openrouter.ai/docs/api/reference/limits | Sin fecha |
| 9 | El límite es por cuenta y varias claves no suman | Correcta | https://openrouter.ai/docs/api/reference/limits | Sin fecha |
| 10 | Saldo negativo devuelve 402 también en gratuitos | Correcta | https://openrouter.ai/docs/api/reference/limits | Sin fecha |
| 11 | Endpoint `/key` | Correcta; además devuelve `free_model_daily_requests` (`used`, `limit`, `remaining`) y `rate_limit` está obsoleto | https://openrouter.ai/docs/api/reference/limits | Sin fecha |
| 12 | Array `models` como cadena de reserva | Correcta: se pasa al siguiente ante límites, caídas o contexto; no se documenta un máximo; se cobra el modelo usado | https://openrouter.ai/docs/guides/routing/model-fallbacks | Sin fecha |
| 13 | Enrutador `openrouter/free` | Correcta: elige un modelo gratuito que cumpla los requisitos; publicado el 1/2/2026 | https://openrouter.ai/docs/guides/routing/routers/free-router ; https://openrouter.ai/openrouter/free | 1/2/2026 |
| 14 | Para usar gratuitos hay que permitir que los proveedores registren o entrenen | Desactualizada: hay ajustes separados para gratuitos; si no se permiten proveedores que entrenan, no se enruta a ellos; 9 de 19 gratuitos pueden entrenar | https://openrouter.ai/docs/guides/privacy/provider-logging ; https://www.truefoundry.com/blog/openrouter-free-models-whats-actually-free-and-what-it-costs-you | Sin fecha; 8/10/2026 (datos del 5/10/2026) |
| 15 | `provider.data_collection: "deny"` | Correcta (documentación del SDK de OpenRouter); según una fuente secundaria, el enrutado por política podría depender del plan | https://openrouter.ai/docs/client-sdks/typescript/models/datacollection.md | Sin fecha |
| 16 | Los intentos fallidos cuentan para el límite diario | No verificable en fuente oficial; una fuente secundaria dice que sí | https://www.truefoundry.com/blog/openrouter-free-models-whats-actually-free-and-what-it-costs-you | 8/10/2026 |
| 17 | Ganchos HTTP de tusd (`pre-create`, `post-finish`, `post-terminate`, reenvío de `Authorization`) | Correcta, pero `post-finish` no es bloqueante; existe `pre-finish` bloqueante; formato JSON `Type`/`Event` y respuesta `HTTPResponse`/`RejectUpload` | https://tus.github.io/tusd/advanced-topics/hooks/ | Sin fecha |
| 18 | `forward_auth` de Caddy | Correcta: petición GET con `X-Forwarded-Method` y `X-Forwarded-Uri`; 2xx continúa; `copy_headers` copia a la petición | https://caddyserver.com/docs/caddyfile/directives/forward_auth | Sin fecha |
| 19 | Better Auth con plugin JWT y JWKS | Correcta: `/api/auth/jwks`, `/token`, 15 minutos, claves en la tabla `jwks` cifradas con AES-256-GCM. Versiones actuales: better-auth 1.7.14, next 16.4.3, next-intl 4.14.9. Compatibilidad del plugin de administración con Next 16: no verificada | https://www.better-auth.com/docs/plugins/jwt ; https://registry.npmjs.org | Sin fecha; 31/10/2026 |
| 20 | Gotenberg, ruta LibreOffice: PDF/A, PDF/UA, rangos, `singlePageSheets`, formularios, notas, diapositivas ocultas, contraseña | Correcta (`pdfa`, `pdfua`, `nativePageRanges`, `singlePageSheets`, `exportFormFields`, `exportNotesPages`, `exportHiddenSlides`, `password`, `generateTaggedPdf`). Solo produce PDF. Macros desactivadas y, desde la 8.34, sin contenido enlazado | https://gotenberg.dev/docs/convert-with-libreoffice/convert-to-pdf | Sin fecha |
| 21 | Gotenberg, ruta Chromium: página única, PDF etiquetado, medio, espera, esquema de color | Correcta (`singlePage`, `generateTaggedPdf`, `generateDocumentOutline`, `emulatedMediaType`, `emulatedMediaFeatures`, `waitDelay`); además trae campos Factur-X (`facturxXml`) | https://gotenberg.dev/docs/convert-with-chromium/convert-url-to-pdf | Sin fecha |
| 22 | Filtros de salida de Gotenberg | Hecho no citado en el documento: desde la 8.32 los filtros por clase de IP existen pero vienen desactivados; afectan a Chromium, LibreOffice, `downloadFrom` y webhooks | https://newreleases.io/project/github/gotenberg/gotenberg/release/v8.32.0 | Primer semestre de 2026 |
| 23 | OCRmyPDF «por la ruta sin Ghostscript» | Correcta desde la v17: rasterizador pypdfium2 y `--pdfa-backend internal`, que nunca usa Ghostscript y falla (código 10) si el validador no aprueba. Versión actual 17.13.0, MPL-2.0 | https://ocrmypdf.readthedocs.io/en/latest/installation.html ; https://ocrmypdf.readthedocs.io/en/latest/releasenotes/version17.html ; https://pypi.org/project/ocrmypdf/ | 28/9/2026 |
| 24 | OCRmyPDF `--clean` | Correcta (usa unpaper, opcional) | https://ocrmypdf.readthedocs.io/en/latest/cookbook.html | Sin fecha |
| 25 | OCRmyPDF `--remove-background` | No verificable con certeza: la guía actual la describe y notas e incidencias antiguas la dan por retirada | https://ocrmypdf.readthedocs.io/en/latest/cookbook.html ; https://github.com/ocrmypdf/OCRmyPDF/issues/884 | Sin fecha |
| 26 | Dependencias externas de OCRmyPDF | Correcta: unpaper (opcional, para `--clean`), pngquant (opcional, con `-O2` y `-O3`) y jbig2enc (opcional); fpdf2 (LGPL-3.0) y uharfbuzz son obligatorias. Licencias de unpaper y pngquant (GPL) y jbig2enc (Apache-2.0): conocidas, no reverificadas hoy | https://ocrmypdf.readthedocs.io/en/latest/installation.html ; https://pypi.org/project/fpdf2/ | Sin fecha |
| 27 | EmbedPDF hace redacción real, anotaciones y formularios | Parcial: licencia MIT (2.15.1) y la documentación habla de eliminación permanente, pero no explica qué ocurre con imágenes y trazados. No verificable sin pruebas | https://www.embedpdf.com/docs/react/plugins/plugin-redaction ; https://registry.npmjs.org/@embedpdf/core | Sin fecha |
| 28 | @cantoo/pdf-lib, pypdfium2 y qpdf | Correcta: @cantoo/pdf-lib 2.11.1 MIT; pypdfium2 5.14.0 BSD-3-Clause y Apache-2.0. qpdf Apache-2.0 por conocimiento, no reverificado | https://registry.npmjs.org ; https://pypi.org/project/pypdfium2/ | 4/10/2026 |
| 29 | pikepdf `add_overlay`, `add_underlay` y esquemas | Correcta (pikepdf 10.17.0, MPL-2.0; esquemas con `open_outline()`) | https://pikepdf.readthedocs.io/en/latest/topics/overlays.html ; https://pikepdf.readthedocs.io/en/latest/topics/outlines.html | 11/10/2026 |
| 30 | Docling: licencias | Correcta con matiz: código MIT (2.145.0); modelo de maquetación Apache-2.0; TableFormer CDLA-Permissive-2.0 o Apache-2.0; TableFormerV2 sin ficha de licencia | https://pypi.org/project/docling/ ; https://huggingface.co/docling-project/docling-models ; https://huggingface.co/docling-project/TableFormerV2/discussions/3 | 29/10/2026 |
| 31 | Docling: calidad de PDF a DOCX y XLSX | Optimista: Docling extrae estructura y no genera DOCX fiel al diseño. Memoria en CPU para 225 páginas: unos 2,5 GB (backend pypdfium) o 6,2 GB (nativo) | https://arxiv.org/abs/2408.09869 (resumen en hyper.ai) | 2024 |
| 32 | pyHanko: firma interrumpida, B-LTA, análisis de diferencias, listas de confianza de la UE | Correcta: pyHanko 0.38.0 (MIT) cubre B-B a B-LTA, PKCS#11, firma interrumpida, análisis de diferencias, validación AdES y listas de confianza de la UE (en pyHanko, no solo en certvalidator, 0.33.0). DocMDP: por conocimiento, no reverificado | https://github.com/MatthiasValvekens/pyHanko ; https://pypi.org/project/pyhanko/ | 17/10/2026 |
| 33 | pillow-heif incluye x265 y queda bajo GPLv2 | Correcta: libheif y libde265 LGPLv3, x265 GPLv2; los wheels son GPLv2 | https://raw.githubusercontent.com/bigcat88/pillow_heif/master/LICENSES_bundled.txt | 11/10/2026 (versión 1.8.1) |
| 34 | libheif solo para decodificar | Correcta por licencias (LGPLv3 con libde265); la compilación sin x265 es una opción de compilación conocida, no reverificada | Misma fuente | 11/10/2026 |
| 35 | Patentes HEVC | Riesgo confirmado: HEVC Advance cobra por usuario a quien presta servicios en la nube con decodificadores o codificadores HEVC; la página no menciona HEIF. Aplicación a HEIC: no verificable (abogado) | https://accessadvance.com/topic-what-do-we-license/ | 2026 |
| 36 | Facturae 3.2.2 es la versión vigente | Correcta: XSD oficial 3.2.2; no se encontró una versión posterior | https://www.facturae.gob.es/content/dam/facturae/formato/versiones/Facturaev3_2_2.xml | 2017 |
| 37 | Perfiles Factur-X y ZUGFeRD | Correcta por conocimiento (MINIMUM, BASIC WL, BASIC, EN 16931, EXTENDED, XRECHNUNG); Gotenberg expone `facturxConformanceLevel` | https://gotenberg.dev/docs/convert-with-chromium/convert-url-to-pdf | Sin fecha |
| 38 | KoSIT Validator con escenarios oficiales de EN 16931, XRechnung, Peppol BIS y Factur-X | Parcialmente incorrecta: Apache-2.0, Java 11 o posterior, la 1.6 solo con mantenimiento; configuraciones públicas solo de XRechnung y Peppol BIS | https://github.com/itplr-kosit/validator | Sin fecha |
| 39 | Schematron de EN 16931 con EUPL-1.2 | Correcta (versión 1.3.17) | https://github.com/ConnectingEurope/eInvoicing-EN16931 | 9/10/2026 |
| 40 | Licencias de los Schematron de XRechnung y Peppol | No verificable hoy: el repositorio de Peppol no muestra licencia | https://github.com/OpenPEPPOL/peppol-bis-invoice-3 | Sin fecha |
| 41 | drafthorse y factur-x | Correcta: drafthorse 2025.2.0 Apache; factur-x 7.9 BSD | https://pypi.org/project/drafthorse/ ; https://pypi.org/project/factur-x/ | 15/9/2025; 30/10/2026 |
| 42 | Veri*factu | Correcta pero incompleta: el RDL 15/2025 aplaza la obligación de los usuarios al 1/1/2027 (sociedades) y al 1/7/2027 (resto); los productores siguen obligados desde el 29/7/2025 | https://www.legaltoday.com/actualidad-juridica/noticias-de-derecho/nueva-prorroga-verifactu-no-sera-obligatorio-hasta-2027-para-sociedades-y-otros-contribuyentes-2025-12-04/ | 4/12/2025 |
| 43 | Factura electrónica obligatoria entre empresas | No recogida en el documento: RD 238/2026 (25/3/2026) y Orden HAC/1028/2026 (BOE del 5/10/2026, en vigor al día siguiente), que inicia los plazos de la Ley 18/2022 (12 meses para más de 8 M€ y 24 para el resto, según su disposición final 8.ª) y obliga a enviar copia en UBL a la solución pública | https://www.boe.es/boe/dias/2026/10/05/pdfs/BOE-A-2026-20587.pdf ; https://www.boe.es/eli/es/rd/2026/03/25/238 | 5/10/2026 |
| 44 | Kokoro (Apache-2.0) | Correcta para el modelo; incompleta: el español usa espeak-ng y `misaki[en]` instala `phonemizer-fork` (GPL-3.0+); kokoro 0.9.4 es de abril de 2025 | https://pypi.org/project/kokoro/ ; https://pypi.org/project/phonemizer-fork/ ; https://github.com/hexgrad/misaki | 5/4/2025; 30/1/2025 |
| 45 | faster-whisper y modelos Whisper | Correcta: faster-whisper 1.2.1 MIT; pesos de Whisper MIT por conocimiento | https://pypi.org/project/faster-whisper/ | 31/10/2025 |
| 46 | Modelos de rembg con licencia comercial | Riesgo no señalado: el modelo por defecto es `bria-rmbg` (RMBG-2.0), que exige acuerdo de pago; BiRefNet aparece como MIT en sus fichas; U-2-Net e IS-Net no verificados hoy | https://github.com/danielgatis/rembg ; https://huggingface.co/briaai/RMBG-1.4 | Sin fecha |
| 47 | fastembed con `intfloat/multilingual-e5-small` | Incorrecta: no está en la lista; sí `paraphrase-multilingual-MiniLM-L12-v2` (Apache-2.0) y `multilingual-e5-large` (MIT). fastembed 0.9.1 Apache-2.0 | https://qdrant.github.io/fastembed/examples/Supported_Models/ | Sin fecha |
| 48 | Calibre, pandoc, MuseScore, LibreDWG, OpenSCAD y FluidSynth | Correcta por conocimiento (GPL-3.0, GPL-2.0+, GPL-3.0, GPL-3.0+, GPL-2.0 y LGPL-2.1+); no reverificadas hoy | — | — |
| 49 | draw.io desktop | Incorrecta en su clasificación: es GPL-3.0 y el documento no lo pone en la lista de GPL externos | https://github.com/jgraph/drawio-desktop | Sin fecha |
| 50 | Tectonic | Correcta: MIT (0.17.0). Modo sin descargas: no verificado en la documentación | https://crates.io/crates/tectonic | 27/7/2026 |
| 51 | usd-core, OpenCascade, assimp, lib3mf y manifold3d | Correcta con matiz: usd-core usa LicenseRef-TOST-1.0, fuera de la lista permitida; cadquery-ocp Apache-2.0 con OCCT LGPL-2.1 con excepción; pyassimp ISC; lib3mf BSD; manifold3d Apache-2.0 | https://pypi.org/project/usd-core/ ; https://pypi.org/project/cadquery-ocp/ ; https://pypi.org/project/lib3mf/ ; https://pypi.org/project/manifold3d/ | 2026 |
| 52 | veraPDF | Correcta: doble licencia GPL-3.0+ y MPL-2.0 | https://github.com/veraPDF/veraPDF-library | Sin fecha |
| 53 | Bancos de sonidos con licencia comercial | No verificado hoy | — | — |
| 54 | SheetJS Community Edition | Correcta: Apache-2.0; el registro de npm se quedó en 0.18.5 con CVE-2023-30533 y CVE-2024-22363; hay que instalarla desde cdn.sheetjs.com | https://git.sheetjs.com/sheetjs/sheetjs/issues/2961 ; https://cvefeed.io/vuln/detail/CVE-2023-30533 | 2023–2024 |
| 55 | TipTap «sin extensiones de pago» | Correcta con implicación: núcleo y extensiones como tabla de contenidos, matemáticas, detalles y emojis son MIT (3.32.2); Pages es de pago y está en un registro privado | https://registry.npmjs.org/@tiptap/core ; https://tiptap.dev/docs/pages/getting-started/install.md | 31/10/2026 |
| 56 | qr-code-styling, Konva y mammoth | Correcta: MIT (1.9.2), MIT (10.9.0) y BSD-2-Clause (1.13.0) | https://registry.npmjs.org | 31/10/2026 |
| 57 | ffmpeg.wasm incluye librerías GPL | Correcta: `@ffmpeg/core` es GPL-2.0-or-later | https://registry.npmjs.org/@ffmpeg/core | 31/10/2026 |
| 58 | ezdxf | Riesgo no señalado: su salida a PDF usa PyMuPDF y el extra `draw` lo instala | https://ezdxf.readthedocs.io/en/stable/tutorials/image_export.html ; https://pypi.org/project/ezdxf/ | 16/10/2026 |
| 59 | extract-msg y xmlsig | Riesgo no señalado: extract-msg es GPL; xmlsig se clasifica como AGPL-3.0 en PyPI | https://pypi.org/project/extract-msg/ ; https://pypi.org/project/xmlsig/ | 31/10/2026; 10/5/2023 |
| 60 | bgcode: implementación propia a partir de la especificación de Prusa | No verificable: libbgcode es AGPL-3.0-only y no se localizó el texto de la especificación ni su licencia | https://src.opensuse.org/pool/libbgcode/src/branch/factory/libbgcode.spec | Sin fecha |
| 61 | Foto del DNI de 26 × 32 mm | Correcta en la medida (32 mm de alto por 26 de ancho), pero el RD 1553/2005 que la fijaba está derogado desde el 2/4/2025 por el RD 255/2025; no se pudo leer su artículo sobre la foto. Hojas de requisitos de noviembre de 2025 mantienen 32 × 26 | https://www.boe.es/buscar/act.php?id=BOE-A-2005-21163 ; https://www.sanroque.es/sites/default/files//files_noticias/2025/11/12/REQUISITOS%20DNI-2.pdf | 2/4/2025; 11/2025 |
| 62 | Foto del pasaporte | No verificable hoy en el BOE; fuentes comerciales indican la misma medida | — | — |
| 63 | Formato UDF de UYAP | Correcta: ZIP con `content.xml` (y metadatos); editor oficial en Java; no hay conversor libre maduro | https://dev.to/ox3adie1/how-i-built-a-browser-based-udf-to-pdf-converter-for-turkish-legal-documents-i5o ; https://pypi.org/project/udf-tools/ | Sin fecha |
| 64 | Acta Europea de Accesibilidad | Aplicable desde el 28/6/2025 (Ley 11/2023); las microempresas que prestan servicios están exentas; el comercio electrónico está incluido | https://www.cuatrecasas.com/es/latam/propiedad-intelectual/art/claves-proxima-entrada-vigor-ley-accesibilidad-espana ; https://www.fieldfisher.com/es-es/locations/espana/actualidad/accesibilidad-obligatoria-claves-de-la-transposicion-accesibility-act | 2025 |
| 65 | Cloudflare limita el cuerpo de cada petición | Correcta: 100 MB en Free y Pro, 200 MB en Business y 500 MB en Enterprise | https://developers.cloudflare.com/workers/platform/limits/ | Sin fecha |
| 66 | Cloudflare corta conexiones inactivas | Correcta; el tiempo de espera de respuesta del origen es hoy de 125 s (solo Enterprise lo amplía) | https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-524/ | Sin fecha |
| 67 | Cloudflare delante de vídeo y archivos grandes | Hecho no citado: las condiciones del CDN en Free, Pro y Business no permiten servir vídeo ni una proporción desproporcionada de archivos grandes | https://blog.cloudflare.com/updated-tos/ ; https://developers.cloudflare.com/fundamentals/reference/policies-compliances/delivering-videos-with-cloudflare/ | 2023; sin fecha |
| 68 | GitHub Container Registry y Actions | Hecho no citado: el registro de contenedores es hoy gratis (con aviso de un mes antes de cobrar); Actions incluye 2.000 minutos al mes en repositorios privados del plan gratuito | https://docs.github.com/en/billing/concepts/product-billing/github-packages ; https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/ | Sin fecha; 16/12/2025 |
| 69 | Datos estructurados `FAQPage` | Desactualizada como ventaja: Google retiró los resultados enriquecidos de FAQ en mayo de 2026 | https://www.searchenginejournal.com/google-drops-faq-rich-results-from-search/574429/ | Mayo de 2026 |
| 70 | Smokescreen con lista por cliente | Matiz: identifica a los clientes por certificado TLS; imagen oficial `ghcr.io/stripe/smokescreen` | https://github.com/stripe/smokescreen | Sin fecha |
| 71 | Turnstile no exige consentimiento de cookies | No verificable en fuente oficial: fuentes secundarias lo tratan como estrictamente necesario, aunque se ha visto la cookie `cf.turnstile.u` | https://friendlycaptcha.com/insights/cloudflare-turnstile-gdpr/ ; https://discourse.webflow.com/t/cookie-consent-compliance-cf-turnstile-u-cookie-loading-before-consent/326947 | Sin fecha |
| 72 | Recuento del catálogo | Hecho: unos 330 slugs distintos en la sección 7 (script sobre el documento), frente a las «unas 150 herramientas» del encargo | Documento 1, sección 7 | 31/10/2026 |

---

## 4. Presupuesto de recursos del VPS

Todas las cifras son estimaciones (juicio, confianza media o baja) salvo las de Docling, que salen de su artículo técnico. Deben sustituirse por las medidas de la prueba de carga de 16.1 en cuanto existan.

### 4.1 El diseño original en el peor caso simultáneo

Con la concurrencia de la sección 5.4 original y los hilos por defecto de cada motor:

- **RAM:** unos 55 GB si coinciden los picos de todos los grupos (4 trabajos de PDF grandes, 2 OCR con veraPDF, Docling, 2 transcripciones con Whisper `medium`, 2 mallas de 10 millones de triángulos, OpenCascade, Gotenberg, PostgreSQL y el resto), frente a 32 GB.
- **CPU:** unos 59 hilos en 8 vCPU. OCRmyPDF lanza por defecto tantos procesos como núcleos, y torch, FFmpeg y faster-whisper usan todos los núcleos: 2 OCR × 8 + Docling × 8 + 2 trabajos de `av` × 8 suman 40 hilos solo en esos grupos.
- **Conclusión:** 8 vCPU y 32 GB no bastan para el catálogo completo con esa concurrencia. Sí bastan hasta F4 con la concurrencia y los hilos de la tabla siguiente.

### 4.2 Presupuesto por servicio con la concurrencia revisada (P-15)

| Servicio | Concurrencia (8 / 16 vCPU) | RAM pico estimada | `mem_limit` propuesto (8 / 16 vCPU) | `cpus` (8 / 16) | Imagen aprox. |
| --- | --- | --- | --- | --- | --- |
| Coolify (panel, base de datos, Redis, tiempo real, Traefik) | — | 1–1,5 GB | sin límite | — | 2 GB |
| `web` (Next.js) | — | 0,3–0,8 GB | 1 / 1,5 GB | 1 / 2 | 0,3 GB |
| `api` (2 o 4 procesos uvicorn) | — | 0,4–1 GB | 1 / 2 GB | 1 / 2 | 1,2 GB (base Python común) |
| `apiint` y `beat` | — | 0,3–0,6 GB | 0,75 GB | 0,5 | misma imagen |
| `upload` (tusd) | — | 0,1–0,2 GB | 0,25 GB | 0,5 | 0,05 GB |
| `files` (Caddy) | — | 0,05–0,1 GB | 0,25 GB | 0,5 | 0,05 GB |
| `egressai` y `egressweb` | — | 0,1 GB | 0,25 GB cada uno | 0,25 | 0,05 GB |
| `postgres` con pgvector | — | 1,5–3 GB | 2,5 / 4 GB | 1 / 2 | 0,5 GB |
| `valkey` | — | 0,1–0,5 GB | 0,5 / 1 GB | 0,5 | 0,05 GB |
| `umami` | — | 0,3 GB | 0,5 GB | 0,5 | 0,5 GB |
| `gotenberg` (LibreOffice y Chromium) | 1 instancia | 1–3 GB | 3 / 4 GB | 2 / 3 | 1,5–2 GB |
| `gotenbergweb` (Chromium) | 1 instancia | 0,5–1,5 GB | 1,5 / 2 GB | 1 | misma imagen |
| `workerpdf` | 3 / 6 | 0,3–1 GB por trabajo, con `RENDER_MAX_PIXELS` | 3 / 6 GB | 3 / 6 | 1,5 GB |
| `workerocr` (2 hilos) | 1 / 2 | 1,5–2,5 GB por trabajo (Tesseract y veraPDF en Java) | 3 / 6 GB | 2 / 4 | 2–3 GB |
| `workeroffice` (LibreOffice con unoserver, Calibre) | 2 / 3 | 0,5–1,5 GB por trabajo | 3 / 4 GB | 2 / 3 | 2,5 GB |
| `workerconvert` (Docling, 2 hilos) | 1 / 1 | 2,5–6 GB (2,5 GB con backend pypdfium y 6,2 GB con el nativo para 225 páginas) | 5 / 8 GB | 2 / 2 | 3–4 GB |
| `workermedia` | 2 / 3 | 0,5–1,5 GB (RAW y PSD grandes) | 3 / 4 GB | 2 / 3 | 1,5 GB |
| `workerai` | 4 / 6 | 0,2 GB por trabajo más 0,5 GB de fastembed | 2 / 3 GB | 1 / 2 | 1,5 GB |
| `workersign` | 1 / 1 | 0,3–0,6 GB | 1 GB | 1 | 1,2 GB |
| `workerav` (FFmpeg, faster-whisper, Kokoro; 2 hilos) | 2 / 3 | 1–2,5 GB (Whisper `small` a `medium`; FFmpeg 0,5–1 GB) | 3 / 6 GB | 4 / 6 | 3–4 GB |
| `workerutils` (KoSIT en Java, MuseScore, draw.io, Tectonic) | 2 / 2 | 0,5–1,5 GB | 3 / 4 GB | 2 | 3–4 GB |
| `workermesh` | 1 / 2 | 2–4 GB (10 millones de triángulos) | 4 / 6 GB | 1 / 2 | 1 GB |
| `workercad` (OpenCascade, OpenSCAD, LibreDWG) | 1 / 1 | 1–4 GB | 4 / 6 GB | 1 | 2 GB |

**Totales:**

- **Hasta F4** (sin `utils`, `mesh` ni `cad`), en 8 vCPU y 32 GB: suma de `mem_limit` de unos 34,8 GB, más 1,5 GB de Coolify, unos 36 GB. Es un 13 % por encima de la RAM: aceptable porque los picos de Docling, OCR y Whisper rara vez coinciden, con `memswap_limit` igual a `mem_limit` y `oom_score_adj` para que, si se agota la memoria, muera antes un worker que PostgreSQL (P-15).
- **Catálogo completo:** en 8 vCPU y 32 GB serían unos 47 GB de límites, un 48 % por encima: no cabe. En 16 vCPU y 64 GB, unos 72 GB, un 13 % por encima: cabe con las mismas salvaguardas.
- **CPU bajo carga plena hasta F4:** los grupos intensivos suman unos 17 `cpus` en 8 vCPU (unas 2 veces más de lo que hay): cada trabajo tarda el doble, pero nada se cae. `cpu_shares` da prioridad a las páginas y a `workerpdf`.
- **Disco de imágenes:** unos 25 a 30 GB por versión, el doble mientras Coolify conserva la anterior.

**Tamaño:**

| Etapa | Mínimo | Recomendado |
| --- | --- | --- |
| Lanzamiento y hasta F4 | 8 vCPU dedicadas, 32 GB, 400 GB NVMe | 8 vCPU dedicadas, 32 GB, 400 GB NVMe más un volumen para archivos |
| Catálogo completo (F5 a F7) | 12 vCPU dedicadas, 48 GB, 1 TB NVMe | 16 vCPU dedicadas, 64 GB, 1 TB NVMe (o 400 GB más un volumen de 600 GB) |

¿Bastan 8 vCPU? Hasta F4, sí, con hilos fijados y la concurrencia revisada. Para el catálogo completo con vídeo, mallas y CAD, no: un vídeo de una hora o una malla grande ocupan sus núcleos durante minutos u horas.

### 4.3 Tiempos esperados por tipo de trabajo

Estimaciones (confianza baja) con los hilos de la tabla, a medir con k6:

| Trabajo | Tiempo estimado |
| --- | --- |
| Herramientas de navegador | De instantáneo a unos segundos, según el dispositivo |
| comprimir-pdf, 20 páginas con fotos | 2–10 s |
| word-a-pdf, 20 páginas | 2–8 s; una hoja de cálculo enorme, hasta 1 minuto |
| ocr-pdf, 10 páginas escaneadas a 300 ppp | 20–60 s |
| pdf-a-word con Docling, 20 páginas | 20–60 s en CPU |
| ogg-a-mp3, nota de voz de 2 minutos | menos de 2 s |
| transcribir-audio, 10 minutos con `small` en `int8` | 2–5 minutos |
| mov-a-mp4 de 1 GB remultiplexando | 10–30 s; recodificar una hora de 1080p con 2 hilos, 1–2 horas |
| step-a-stl, ensamblaje medio | 5–60 s |
| validar-factura-electronica con KoSIT en modo servicio | 1–3 s |
| Petición a un modelo gratuito de OpenRouter | 5–60 s, más la espera del límite por minuto |

### 4.4 Colas y picos de tráfico

- **Capacidad por hora en 8 vCPU** (juicio): unos 1.800 trabajos ligeros de PDF, unos 600 de Office (LibreOffice serializa en Gotenberg), unos 90 OCR y unos 90 PDF a Word.
- **Pico típico** (salir destacado en Menéame, Reddit o una red social): unas 30.000 visitas en 3 horas. Si un 8 % usa una herramienta de servidor, son unos 800 trabajos por hora, en su mayoría ligeros: caben. Los pesados (un 10 %, unos 80 por hora) rozan la capacidad de OCR y PDF a Word.
- **Qué pasa con el diseño original:** las colas crecen sin límite, los anónimos esperan indefinidamente y una transcripción de horas bloquea las notas de voz en el mismo grupo.
- **Qué pasa con los parches:** la guarda de colas responde `QUEUE_FULL` a anónimos y gratuitos y ofrece la versión de navegador; las colas `light` y `heavy` separan lo rápido de lo lento; las páginas HTML se sirven desde la caché de Cloudflare, así que el pico de visitas no llega a Next.js (P-10, P-15, P-51).

### 4.5 Evolución del disco

Volumen residente ≈ suma de entrada, temporal y salida de los trabajos vivos: 1 hora para anónimos y 24 horas para registrados. Ejemplo (juicio):

- 5.000 trabajos al día, 60 % anónimos y 40 % registrados, con 10 MB de entrada y 10 MB de salida de media: unos 40 GB de registrados y unos 2,5 GB de anónimos.
- 20 vídeos Pro al día con 1 GB de entrada, 1 GB de salida y 1 GB de temporal: unos 60 GB más.
- Imágenes de Docker (dos versiones), unos 60 GB; base de datos y copias locales, unos 20 GB; logs, 2 GB; swap, 8 GB; sistema, 15 GB.
- **Total:** unos 200 GB con vídeo. 300 GB quedan justos con la guarda al 85 %; 400 GB dan margen hasta F4, y con vídeo y 3D conviene 1 TB.

### 4.6 Riesgo operativo

- **Punto único de fallo:** un VPS y un disco. Es una decisión cerrada y aceptable al principio si la recuperación está probada.
- **Diseño original:** una copia diaria y la remota opcional. Pérdida de datos de hasta 24 horas, o total si se pierde el VPS. Tiempo de recuperación sin definir y sin secretos copiados: en la práctica, días.
- **Con los parches (P-11):** pérdida máxima de 6 horas, copia remota obligatoria con secretos cifrados y token del sello, y un objetivo de recuperación de menos de 4 horas con simulacro trimestral. Stripe es la fuente de verdad de las suscripciones, así que perder unas horas de altas es asumible.
- **Si se quiere bajar a minutos de pérdida:** archivado continuo de WAL a SFTP. No lo he añadido porque complica la operación y no compensa en el lanzamiento.

---

## 5. Decisiones que conviene reabrir

### 5.1 Decisión 6: pagos con Stripe en modo test

- **Problema demostrable:** en modo test no se cobra. Si el objetivo incluye ingresos tempranos, la decisión lo impide por definición, y además deja sin validar el precio, que tampoco está definido (H-48).
- **Coste de mantenerla:** cero ingresos y ningún dato de conversión mientras dure.
- **Coste de cambiarla:** ningún cambio de código (`PaymentProvider` ya existe); sí trabajo legal y fiscal: términos y política de reembolsos, alta en la ventanilla única de IVA si se vende a consumidores de otros países de la UE, registros en Stripe Tax y atención de cobros y devoluciones.
- **Propuesta:** mantener el modo test durante la construcción y pasar a producción en el lanzamiento público, con el paso 11 de §13.3 (P-53).

### 5.2 Decisiones que se mantienen, con una condición

No hay otro bloqueo demostrable. Tres decisiones se sostienen solo si se cumple lo que indico:

- **Decisión 7 (Cloudflare delante de todo):** se mantiene mientras el vídeo sea solo para Pro y su volumen sea pequeño. Las condiciones del CDN de Cloudflare no permiten servir vídeo ni una proporción desproporcionada de archivos grandes en Free, Pro y Business. Plan B, que no aplico: `files` y `upload` sin proxy (DNS-only) en una segunda IP del VPS, con certificado propio y límites en Caddy y tusd. Coste del plan B: una IPv4 adicional, perder el WAF y la protección de Cloudflare en esos dos subdominios y exponer esa IP.
- **Decisión 3 (IA solo con modelos gratuitos):** se mantiene con `data_collection: "deny"` (H-05) y con la IA anunciada como beta. Si la IA llega a ser lo que vende Pro, el cupo de 1.000 peticiones diarias no escala, y la interfaz `LLMProvider` permite pasar a modelos de pago con retención cero: sería una decisión con coste.
- **Decisión 1 (un solo VPS):** se mantiene con 16 vCPU y 64 GB para el catálogo completo (apartado 4). El límite real es el disco local (§4.7).

---

## 6. Propuesta de MVP y reordenación de fases

### 6.1 Criterios

- Primero, lo más buscado que cuesta poco: las herramientas de navegador no gastan servidor, no consumen cuota y son el mejor argumento de privacidad frente a PDF24.
- Las de servidor ligeras, con cuotas generosas (H-19).
- Pro con valor claro desde el primer día: archivos de hasta 1 GB, lotes de 100 archivos, OCR, PDF a Word, más tareas pesadas y prioridad en las colas. No depende de la IA, cuyo cupo no escala.
- Fuera del lanzamiento: lo que tiene riesgo legal sin revisar (firma digital con sello, facturas, HEVC), lo que cuesta mucho servidor (vídeo, 3D, CAD) y la IA (cupo y RGPD).

### 6.2 Lista de lanzamiento (§17.1, P-57)

| Grupo | Herramientas | Motivo |
| --- | --- | --- |
| Navegador, PDF | unir, dividir, girar, eliminar páginas, extraer páginas, organizar, numerar, marca de agua, editar, rellenar, jpg-a-pdf, png-a-pdf, imagenes-a-pdf, pdf-a-jpg, pdf-a-png, pdf-a-imagenes, generar-contrasena | Búsquedas frecuentes, coste cero, privacidad |
| Navegador, imágenes (de F5) | png-a-jpg, webp-a-jpg, comprimir-imagen, redimensionar-imagen | Búsquedas frecuentes, coste cero |
| Servidor ligero | comprimir-pdf, convertir-a-pdf, word-a-pdf, excel-a-pdf, ppt-a-pdf, proteger-pdf y desbloquear-pdf (de F2) | Búsquedas frecuentes, segundos de CPU |
| Servidor, audio (de F5) | ogg-a-mp3, opus-a-mp3, m4a-a-mp3, mp4-a-mp3 | Notas de voz de WhatsApp: demanda alta en España y coste mínimo |
| Servidor pesado, ancla de Pro (de F2) | pdf-a-word, ocr-pdf | Búsquedas muy frecuentes y valor claro para Pro |
| Plataforma | Planes y Stripe, cuotas por clase de coste, guardas de disco y de colas, copias remotas | Ingresos y estabilidad |

Son unas 34 herramientas y unas 70 páginas indexables en dos idiomas, cada una con contenido propio. El resto de F1 queda con `noindex` hasta terminarse (§7.22).

### 6.3 Orden de fases

Las fases conservan su número, porque las líneas del catálogo lo citan, pero cambia el orden de ejecución:

1. F1 (núcleo y lista de lanzamiento) y lanzamiento público con Stripe en producción (apartado 5).
2. Resto de F1 y F2 (PDF de servidor).
3. F5 sin vídeo (audio, imágenes, transcripción): búsquedas frecuentes y baratas.
4. F3 (IA): después, porque su cupo diario no escala y conviene medir la demanda.
5. F4 (firma, compartir y facturas): cuando estén hechas las revisiones legales; en facturas, primero validar y visualizar.
6. F6 (utilidades): menos volumen de búsqueda por herramienta.
7. Vídeo de F5: Pro, coste de CPU, patentes y condiciones de Cloudflare.
8. F7 (3D y CAD): nicho y lo que más recursos pide.

**Precio:** está sin definir y no he comprobado precios de la competencia en esta revisión. Mi propuesta es fijar una hipótesis antes del lanzamiento y medirla con Stripe en producción.

---

## 7. Pre-mortem

Seis meses después del lanzamiento, el proyecto ha fracasado. Las cinco causas más probables:

| # | Causa | Cómo pasó | Cambio del documento que lo evita |
| --- | --- | --- | --- |
| 1 | Nunca se lanzó, o se lanzó tarde | El agente intentó cerrar F1 con unas 45 herramientas, toda la infraestructura y un despliegue que no podía hacer; se paró a pedir accesos uno a uno o dio fases por cerradas sin estarlo. El catálogo real eran unos 330 slugs. | §0.1 y cierre en dos niveles (H-01); lista de lanzamiento y orden de fases (H-18); umbral de herramientas desactivadas (H-45) |
| 2 | Sin tráfico orgánico | Cientos de páginas de plantilla con contenido escaso, herramientas apagadas indexadas y alias duplicados; quien llegaba a comprimir-pdf agotaba sus 3 tareas y volvía a PDF24. | Reglas de indexación y contenido mínimo medido en la CI (H-18); cuotas por clase de coste (H-19); herramientas de navegador sin cuota primero |
| 3 | Incidente de seguridad o de privacidad | Un Markdown con `![](/proc/self/environ)` devolvió `FILE_TOKEN_SECRET` y alguien descargó archivos ajenos; una redacción dejó visible una imagen; documentos con datos personales llegaron a proveedores de IA que entrenan. | Matriz de secretos y motores aislados (H-02); mapa de redes y Gotenberg separado (H-08); rasterizar al redactar (H-12); `data_collection: "deny"` (H-05) |
| 4 | Caídas y pérdida de datos | Un pico coincidió con Docling y una transcripción; la RAM se agotó, los trabajos largos se ejecutaron dos veces por el `visibility_timeout`, el disco se llenó y, al perder el VPS, la única copia estaba en él. | Concurrencia, hilos y límites de memoria (H-15); Celery con latidos e intentos (H-14); guardas de disco y colas (H-30); copia remota obligatoria con secretos y simulacro (H-16) |
| 5 | Ingresos insuficientes | Stripe siguió en modo test, el precio no se definió y Pro se apoyó en una IA que con 1.000 peticiones diarias no daba para más de unos pocos clientes; mientras, el VPS grande y los minutos de la CI costaban cada mes. | Decisión 5.1 y paso a producción (H-48); Pro basado en archivos grandes, lotes, OCR y PDF a Word (H-06, H-19); imágenes privadas y CI con filtros (H-36) |

---

## 8. Parches

- Cada parche indica las líneas del documento original que sustituye y trae el texto nuevo completo, listo para pegar.
- Cubren todos los hallazgos bloqueantes, altos y medios, y también los bajos.
- Están aplicados en `super-prompt-conversor-coolify.v2.md`; `CHANGELOG.md` relaciona cada parche con sus hallazgos.
- Si los aplicas a mano, hazlo de abajo arriba, para que los números de línea del original sigan valiendo.
- Los textos de reemplazo van entre `~~~~` para que los bloques de código que contienen se vean bien.

### P-01 · H-01 · §0: qué hacer si los valores siguen sin sustituir

Sustituye la línea 9 del original: «Sustituye estos valores antes de empezar:».

~~~~markdown
Sustituye estos valores antes de empezar. Si al recibir este documento alguno sigue entre llaves, usa los valores de prueba de la sección 0.1, continúa y no publiques nada:
~~~~

### P-02 · H-01 · Nueva §0.1: entradas del propietario

Sustituye la línea 37 del original: «- La paridad es de funciones: no copies textos, diseños, plantillas ni marca de PDF24.».

~~~~markdown
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
~~~~

### P-03 · H-01, H-44, H-45, H-56 · §1: dos cierres por fase, documento troceado, calidad y muestras

Sustituye las líneas 43–68 del original, desde «1. Antes de programar, crea `docs/PLAN.md` con las fases de la sección 17 desglosadas en tareas, y `docs/PROGRESS.md`, que actualizarás al cerrar cada tarea.» hasta «9. Al cerrar cada fase, revisa tu propio trabajo como lo haría un revisor externo exigente (seguridad, licencias, accesibilidad, rendimiento, uso de disco y del presupuesto de IA) y corrige lo que encuentres.».

~~~~markdown
1. Antes de programar:
   - divide este documento en ficheros de `docs/spec/` (uno por sección y uno por apartado del Anexo A) sin cambiar su texto, con un índice en `docs/spec/INDEX.md`; al empezar cada fase, relee las secciones que usa;
   - crea `docs/PLAN.md` con las fases de la sección 17 desglosadas en tareas, y `docs/PROGRESS.md`, que actualizarás al cerrar cada tarea.
2. Comprueba en internet la versión estable actual de cada dependencia e imagen Docker y fíjala; nunca uses `latest`. No te fíes de la memoria para APIs que cambian (Coolify, OpenRouter, tusd, Better Auth, Next.js, Gotenberg, OCRmyPDF).
3. Cada fase tiene dos cierres:
   - **Cierre técnico**, que haces tú y comprueba la CI:
     - pasan todas las pruebas de la fase y de las anteriores;
     - `docker compose up` arranca en local solo con `.env.example`, con los dobles de la sección 0.1;
     - `docker-compose.coolify.yml` pasa `docker compose config` y un arranque de humo en la CI con los mismos healthchecks;
     - Lighthouse CI (perfil móvil, mediana de 3 ejecuciones) da 90 o más en rendimiento y accesibilidad en la portada y en las páginas de herramienta de la fase.
   - **Cierre operativo**, que requiere las entradas de 0.1:
     - con token de la API de Coolify, despliega y comprueba que todos los healthchecks están en verde y que `/readyz` responde 200 en tres comprobaciones separadas por 10 minutos;
     - sin token, deja los pasos y las comprobaciones para el propietario en `docs/DEPLOY-CHECKLIST.md`, anota el cierre operativo como pendiente en `docs/PROGRESS.md` y sigue con la fase siguiente.
4. Haz commit al cerrar cada tarea, con mensajes descriptivos.
5. Si algo no está decidido aquí, elige la opción más simple coherente con este documento y anótala con su motivo en `docs/DECISIONS.md`.
6. Antes de añadir una dependencia, comprueba su licencia contra la sección 11, incluidas sus dependencias transitivas y sus extras (`paquete[extra]`), y regístrala en `docs/LICENSES.md`.
7. Nada de TODO, stubs ni funciones simuladas en el código entregado. Los dobles de 0.1 y los proveedores falsos solo existen con `APP_ENV=development` o en las pruebas.
   - Una herramienta está lista cuando pasa sus pruebas de 16.5 y 16.6 y su página tiene el contenido de 8.2.
   - Si no lo consigue, queda desactivada con su flag y explicas el motivo en `docs/TOOLS.md`.
   - Una fase puede cerrarse con herramientas desactivadas si no superan el 10 % de las de la fase y ninguna está en la lista de lanzamiento (17.1).
8. Prueba cada herramienta con archivos reales en `tests/fixtures`. Necesitas, como mínimo:
   - **PDF:** de texto, escaneado, con tablas, con formulario, cifrado, dañado, de 300 páginas, firmado digitalmente, PDF/A, con marcadores y en color con gráficos vectoriales.
   - **Ofimática y libros:** DOCX, XLSX, PPTX, ODT, RTF, EPUB, MOBI, CBZ y DjVu.
   - **Imagen:** HEIC, TIFF, SVG, AVIF, GIF animado, RAW DNG y PSD.
   - **Correo:** EML, MSG, MBOX y PST.
   - **Audio y vídeo:** OGG Vorbis, OGG Opus (nota de voz), M4A, FLAC, WMA, AMR, MP4, MOV y MKV.
   - **Subtítulos y fuentes:** SRT, ASS, TTF y OTF.
   - **Comprimidos:** RAR y 7Z.
   - **Firmados y facturas:** .csig, .p7m, .xsig, Facturae, UBL, XRechnung (CII y UBL), Peppol BIS y Factur-X/ZUGFeRD.
   - **GPS:** GPX, KML, KMZ, FIT y SHP.
   - **Contactos y calendario:** VCF e ICS.
   - **Diagramas y música:** draw.io, Mermaid, LaTeX, MIDI y MusicXML.
   - **3D:** STL ASCII y binario, OBJ con MTL, 3MF, AMF, PLY, OFF, GLB, FBX, DAE, 3DS, WRL, X3D y USDZ.
   - **CAD:** STEP, IGES, SCAD, DXF y DWG.
   - **Impresión 3D:** G-code, bgcode y .gcode.3mf.
   - **Origen de las muestras:**
     - prefiere generarlas con scripts de `scripts/fixtures/`, con cualquier herramienta aunque su licencia no permita incluirla en el producto (por ejemplo, PrusaSlicer para bgcode o LibreOffice para DOCX), porque las muestras no se distribuyen con el producto;
     - si descargas una, su licencia debe permitir guardarla en el repositorio privado; anota su origen en `tests/fixtures/SOURCES.md`;
     - si no hay forma de conseguir una muestra válida de un formato, la herramienta queda desactivada y lo anotas en `docs/TOOLS.md`.
9. Al cerrar cada fase, revisa tu propio trabajo como lo haría un revisor externo exigente (seguridad, licencias, accesibilidad, rendimiento, uso de disco y del presupuesto de IA) y corrige lo que encuentres.
~~~~

### P-04 · H-03, H-04, H-08, H-10, H-20, H-24, H-25, H-39 · §2: stack con motores y trampas de licencia resueltos

Sustituye las líneas 74–97 del original, desde «| Capa | Tecnología |» hasta «| Observabilidad | Logs JSON, OpenTelemetry, Sentry opcional |».

~~~~markdown
| Capa | Tecnología |
| --- | --- |
| Web | Next.js (App Router), TypeScript, Tailwind, next-intl; salida `standalone` |
| Procesado en navegador | EmbedPDF (PDFium en WebAssembly), `@cantoo/pdf-lib`, jSquash, zxing-wasm (zxing-cpp), OpenCV.js, three.js, glTF Transform con draco3d, mermaid, `@resvg/resvg-wasm` y diff-match-patch; todo en Web Workers |
| Firma en navegador | PKI.js para abrir .p12/.pfx, WebCrypto para firmar y xadesjs para XAdES |
| Subidas | tusd (servidor tus, MIT) con almacenamiento en disco; Uppy con el plugin `@uppy/tus` en el navegador |
| Descargas | Caddy como servidor de archivos con `forward_auth` hacia la API interna |
| Autenticación | Better Auth en Next.js (correo y contraseña, enlace mágico, Google, plugin de administración) con plugin JWT; la API valida los JWT por JWKS |
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| Cola | Celery con Valkey; una cola por grupo de workers, y dos (`light` y `heavy`) en `av` y `office`; Celery beat para tareas periódicas; el estado de los trabajos vive en PostgreSQL, sin backend de resultados |
| Base de datos | PostgreSQL con pgvector |
| Office y HTML a PDF | Gotenberg (LibreOffice y Chromium) en dos instancias: `gotenberg`, sin red, para archivos subidos, y `gotenbergweb`, solo para URL (12.2) |
| Office a formatos que no son PDF | LibreOffice sin interfaz con unoserver (MIT) dentro de `workeroffice`; Gotenberg solo produce PDF |
| Motores PDF | pikepdf, qpdf, pypdfium2, Pillow, OCRmyPDF 17 o posterior (instalado con pip, rasterizador pypdfium2 y `--pdfa-backend internal`, sin Ghostscript) con Tesseract (`tessdata_fast` con todos los idiomas y `tessdata_best` para spa, cat, eus, glg, eng, fra, deu, ita y por), veraPDF, Docling, python-docx, openpyxl, python-pptx, pyHanko, ezdxf (sin el extra `draw`) |
| Audio y vídeo | FFmpeg (compilación LGPL preferente) |
| IA local | faster-whisper (transcripción), Kokoro (voz, pesos Apache-2.0, con fonemas de espeak-ng como proceso externo), fastembed (embeddings) |
| IA remota | OpenRouter, solo modelos gratuitos y solo proveedores que no recogen los datos para entrenar (6.1) |
| Imágenes en servidor | rembg (modelo de 6.4), LibRaw con rawpy, psd-tools, vtracer |
| Utilidades | pandoc (siempre con `--sandbox`), Calibre, libarchive, pysubs2, fontTools, asn1crypto, signxml, defusedxml, GDAL/OGR, gpxpy, fitparse, vobject, icalendar, mail-parser, olefile y compressed-rtf (MSG), draw.io desktop, Tectonic, FluidSynth, charset-normalizer |
| 3D y CAD | lib3mf, trimesh, assimp, manifold3d, fast-simplification, usd-core, shapely, OpenCascade (cadquery/OCP) |
| Programas GPL, solo como proceso externo en servidor | Calibre `ebook-convert`, djvulibre `ddjvu`, poppler `pdftocairo`, pandoc, readpst, MuseScore, OpenSCAD, LibreDWG, draw.io desktop, unpaper, pngquant y espeak-ng |
| Pagos | Stripe Billing y Stripe Tax en modo test |
| Proxy de salida | Smokescreen en dos instancias, `egressai` y `egressweb` (12.2) |
| Antiabuso | Cloudflare Turnstile |
| Analítica | Umami autoalojado (sin cookies), opcional |
| Observabilidad | Logs JSON, OpenTelemetry, Sentry opcional |
~~~~

### P-05 · H-07, H-15 · §3.1: tamaño por fases y cortafuegos que Docker no se salta

Sustituye las líneas 105–111 del original, desde «- Ubuntu Server LTS actual, Docker instalado por el script oficial de Coolify, Coolify v4 en el mismo servidor.» hasta «- Opcional: gVisor (`runsc`) instalado en el host para los workers (secciones 12.1 y 13.1).».

~~~~markdown
- Ubuntu Server LTS actual, Docker instalado por el script oficial de Coolify y Coolify v4, con la versión estable fijada, en el mismo servidor.
- Tamaño (estimación, no medida; ajústalo con las pruebas de carga de 16.1 y la tabla de 5.4):
  - De F1 a F4: 8 vCPU dedicadas, 32 GB de RAM y 400 GB de NVMe, con las concurrencias de la columna de 8 vCPU.
  - Catálogo completo (F5 a F7): 16 vCPU dedicadas, 64 GB de RAM y 1 TB de NVMe (o 400 GB de sistema más un volumen de 600 GB para archivos).
  - Con 16 GB de RAM, desactiva por flag Docling, el modelo `medium` de Whisper, el vídeo y los grupos `mesh` y `cad`.
  - Evita las vCPU compartidas: OCR, vídeo y Docling usan CPU de forma sostenida.
- Swap de 8 GB con `vm.swappiness=10`. Cada contenedor con `mem_limit` lleva `memswap_limit` igual, para que un worker que se pasa de memoria muera en lugar de paginar.
- `unattended-upgrades` activado.
- Cortafuegos:
  - Docker publica los puertos de los contenedores con reglas propias que UFW no filtra. Usa el cortafuegos del proveedor; si no existe, aplica las reglas en la cadena `DOCKER-USER` (o con ufw-docker) y documenta el método en `docs/DEPLOY.md`.
  - 22 solo desde las IP de administración.
  - 80 y 443 solo desde los rangos IP que publica Cloudflare, actualizados por un cron semanal del host, para que nadie se salte el WAF atacando la IP del servidor.
  - 8000, 6001 y 6002 (panel, tiempo real y terminal de Coolify) cerrados al público en cuanto el panel funcione con su dominio a través del proxy, protegido con Cloudflare Access.
- Si el proveedor lo permite, monta un volumen de bloques dedicado en `/srv/{{PRODUCTO}}` para archivos y copias. Así un disco lleno no tumba el sistema.
- Opcional: gVisor (`runsc`) instalado en el host para los workers que procesan archivos (secciones 12.1 y 13.1).
~~~~

### P-06 · H-08, H-26 · §3.2: servicios nuevos (dos Gotenberg, dos proxies, migraciones de Better Auth, Mailpit)

Sustituye las líneas 115–129 del original, desde «| Servicio | Imagen | Dominio | Función |» hasta «| `migrate` | misma imagen que `api` | — | Migraciones Alembic, una sola ejecución |».

~~~~markdown
| Servicio | Imagen | Dominio | Función |
| --- | --- | --- | --- |
| `web` | propia (Next.js) | `{{DOMINIO}}` | Web, SEO, autenticación, panel de usuario y de administración |
| `api` | propia (FastAPI) | `api.{{DOMINIO}}` | API pública |
| `apiint` | misma imagen que `api` | ninguno (solo red interna) | Endpoints internos: ganchos de tusd, autorización de descargas, operaciones |
| `upload` | tusd oficial | `upload.{{DOMINIO}}` | Subidas reanudables a disco |
| `files` | Caddy oficial | `files.{{DOMINIO}}` | Descargas firmadas desde disco |
| `beat` | misma imagen que `api` | — | Tareas periódicas |
| `workerpdf`, `workerocr`, `workeroffice`, `workerconvert`, `workermedia`, `workerai`, `workersign`, `workerav`, `workerutils`, `workermesh`, `workercad` | propias por grupo | — | Workers de Celery |
| `gotenberg` | Gotenberg oficial | — | LibreOffice y Chromium para archivos subidos, sin ninguna salida de red |
| `gotenbergweb` | Gotenberg oficial | — | Chromium para web-a-pdf y captura-web; sale solo por `egressweb` y nunca recibe archivos de usuarios |
| `postgres` | PostgreSQL con pgvector | — | Base de datos |
| `valkey` | Valkey oficial | — | Broker de Celery, límites y cachés |
| `egressai` | Smokescreen oficial (`ghcr.io/stripe/smokescreen`) | — | Salida de `workerai`, solo hacia OpenRouter |
| `egressweb` | Smokescreen oficial | — | Salida de `gotenbergweb`, `workeroffice` y `workersign` hacia IP públicas |
| `umami` | Umami oficial (opcional) | `stats.{{DOMINIO}}` | Analítica sin cookies |
| `migrate` | misma imagen que `api` | — | Migraciones Alembic, una sola ejecución |
| `migrateauth` | misma imagen que `web` | — | Migraciones de Better Auth, una sola ejecución, antes de `migrate` |
| `mailpit` | Mailpit oficial | — | Correo de desarrollo; solo en `docker-compose.yml` |
~~~~

### P-07 · H-36 · §3.3: imágenes siempre privadas y coste de la CI

Sustituye las líneas 133–140 del original, desde «- Las imágenes pesadas (LibreOffice, Docling con Torch solo CPU, OpenCascade, FFmpeg, Whisper) no se construyen en el VPS.» hasta «- Modelos (Whisper, Kokoro, embeddings, rembg, Docling) descargados en tiempo de compilación dentro de la imagen, nunca en tiempo de ejecución, porque los workers no tienen salida a internet.».

~~~~markdown
- Las imágenes pesadas (LibreOffice, Docling con Torch solo CPU, OpenCascade, FFmpeg, Whisper) no se construyen en el VPS.
- GitHub Actions construye cada imagen, la etiqueta con la versión y el SHA, y la publica en GitHub Container Registry.
  - Solo se construyen las imágenes cuyo contexto ha cambiado (filtros por ruta) y con caché de capas.
  - El plan gratuito de GitHub incluye 2.000 minutos al mes para repositorios privados; si el consumo previsto lo supera, es una decisión con coste: pídela al propietario.
- Dos ficheros Compose:
  - `docker-compose.yml`: desarrollo local, con `build:`.
  - `docker-compose.coolify.yml`: producción, solo con `image:` y etiquetas fijas.
- En Coolify, el recurso Docker Compose apunta a `docker-compose.coolify.yml`. Las imágenes son siempre privadas: contienen el código cerrado y programas GPL (Calibre, pandoc y otros) cuya distribución pública obligaría a ofrecer su código fuente. En el VPS, inicia sesión en el registro con un token de solo lectura (`read:packages`) y documenta el paso en `docs/DEPLOY.md`.
- Imagen base común de Python con las dependencias compartidas, y una imagen por grupo de workers encima, para reducir disco y tiempo de compilación.
- Modelos (Whisper, Kokoro, embeddings, rembg, Docling) descargados en tiempo de compilación dentro de la imagen, nunca en tiempo de ejecución, porque los workers no tienen salida a internet.
~~~~

### P-08 · H-13, H-31 · §4.2: pre-finish bloqueante y rechazo de tamaño diferido

Sustituye las líneas 164–183 del original, desde «- El navegador sube con Uppy y `@uppy/tus` a `https://upload.{{DOMINIO}}/files/`, en trozos de 50 MB. Cloudflare limita el cuerpo de cada petición en los planes gratuito y Pro, y los trozos lo evitan.» hasta «- Gancho `post-terminate`: borra la fila y el archivo.».

~~~~markdown
- El navegador sube con Uppy y `@uppy/tus` a `https://upload.{{DOMINIO}}/files/`, en trozos de 50 MB. Cloudflare limita el cuerpo de cada petición a 100 MB en los planes gratuito y Pro, y los trozos lo evitan.
- Opciones de tusd (comprueba los nombres en la versión fijada):
  - almacenamiento en `/srv/files/uploads`;
  - `-base-path /files/`;
  - `-behind-proxy`;
  - CORS solo para `https://{{DOMINIO}}`, permitiendo la cabecera `Authorization`;
  - `-max-size` igual al máximo del plan Pro;
  - ganchos HTTP (`-hooks-http`) hacia `http://apiint:8001/tusd-hooks`, reenviando la cabecera `Authorization` (`-hooks-http-forward-headers`), con los eventos `pre-create`, `pre-finish` y `post-terminate` (`-hooks-enabled-events`).
- Gancho `pre-create` (bloqueante). Rechaza con `RejectUpload` y un mensaje claro en el idioma del usuario si falla alguna de estas comprobaciones:
  1. Valida el JWT del usuario o el token anónimo firmado.
  2. Rechaza las subidas con `SizeIsDeferred: true`: sin tamaño declarado no se puede aplicar el límite del plan.
  3. Comprueba el tamaño declarado contra el plan.
  4. Comprueba la extensión declarada contra las herramientas habilitadas.
  5. Comprueba la cuota diaria y el número de archivos por tarea (9.3).
  6. Reserva espacio en disco (4.5); si no hay, rechaza.
- Gancho `pre-finish` (bloqueante: tusd no confirma el último trozo hasta que responde):
  1. Calcula sha256 leyendo el archivo por bloques.
  2. Detecta el tipo real por bytes.
  3. Registra la fila en `uploads` con propietario, caducidad y estado `ready`.
  4. Si el tipo real no es un formato admitido, la fila queda en `rejected`; `POST /v1/jobs` responde `UNSUPPORTED_FORMAT` y la limpieza de 4.5 borra el archivo.
- `POST /v1/jobs` solo acepta subidas en estado `ready` del mismo propietario.
- Gancho `post-terminate`: borra la fila y libera la reserva de disco; la limpieza borra el archivo si tusd no lo ha hecho.
~~~~

### P-09 · H-32, H-37 · §4.4: cabeceras de aislamiento, CORS y compartir revocable

Sustituye las líneas 193–201 del original, desde «- URL: `https://files.{{DOMINIO}}/d/<job_id>/<archivo>?t=<token>`.» hasta «- Compartir usa la misma ruta sobre `/srv/files/shares` con tokens de hasta `SHARE_MAX_DAYS` días.».

~~~~markdown
- URL: `https://files.{{DOMINIO}}/d/<job_id>/<archivo>?t=<token>`.
- El token es un HMAC-SHA256 con `FILE_TOKEN_SECRET` sobre `job_id`, `archivo`, caducidad y propietario. Caduca en 15 minutos; la interfaz pide URL nuevas a `GET /v1/jobs/{id}` cuando caducan.
- Caddy:
  - hace `forward_auth` a `http://apiint:8001/files/authorize`, que lee la URL original de `X-Forwarded-Uri` y valida el token sin leer el archivo;
  - si recibe 2xx, sirve desde `/srv/files/jobs` con `file_server`;
  - nunca lista directorios;
  - envía `Content-Disposition: attachment`, `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; sandbox` y `Cross-Origin-Resource-Policy: same-site`;
  - responde a CORS solo para `https://{{DOMINIO}}`, para que el visor y las herramientas puedan leer resultados;
  - admite peticiones de rango para audio y vídeo.
- Compartir usa la ruta `/s/<share_id>/<archivo>` sobre `/srv/files/shares`. El token se guarda solo como hash en `shares`; `files/authorize` lo comprueba en la base de datos para poder revocarlo, y caduca como máximo a los `SHARE_MAX_DAYS` días.
- Las condiciones del CDN de Cloudflare en los planes Free, Pro y Business no permiten servir vídeo ni una proporción desproporcionada de archivos grandes. El panel de administración muestra el volumen diario servido por `files` por tipo de archivo, y `docs/DEPLOY.md` describe el plan B de la sección «Decisiones» de la revisión.
~~~~

### P-10 · H-30 · §4.5: reserva de disco y guarda de colas

Sustituye las líneas 205–211 del original, desde «- **Celery beat cada 5 minutos:** borra `jobs/<job_id>` vencidos (1 h anónimos, 24 h registrados), subidas sin terminar de más de 24 h y comparticiones vencidas.» hasta «- `/readyz` informa del uso de disco y el panel de administración lo muestra.».

~~~~markdown
- **Celery beat cada 5 minutos:** borra `jobs/<job_id>` vencidos (1 h anónimos, 24 h registrados), subidas sin terminar de más de 24 h, subidas en estado `rejected` y comparticiones vencidas.
- **Celery beat una vez al día:** busca huérfanos en disco sin fila en base de datos y al revés.
- **Reserva de disco:** `pre-create` reserva en Valkey el tamaño declarado multiplicado por `DISK_RESERVE_FACTOR` (3: entrada, temporal y salida), y la reserva se libera cuando el trabajo termina o caduca. Una subida se acepta solo si el espacio libre menos las reservas vivas sigue por encima de `DISK_MIN_FREE_GB`.
- **Guarda de disco:** si el uso del volumen supera `DISK_MAX_USAGE_PERCENT` (85 %) o el espacio libre baja de `DISK_MIN_FREE_GB`:
  - `pre-create` rechaza nuevas subidas con «Servicio saturado, inténtalo en unos minutos»;
  - las herramientas de navegador siguen funcionando;
  - se avisa por correo a `ADMIN_EMAILS`, como máximo una vez por hora.
- **Guarda de colas:** cada cola tiene `QUEUE_MAX_WAIT_SECONDS_<GRUPO>`. Si la espera estimada (trabajos en cola por duración media de los últimos 30 minutos, dividido por la concurrencia) la supera, `POST /v1/jobs` rechaza a anónimos y gratuitos con `QUEUE_FULL`; la interfaz muestra la espera y ofrece la versión de navegador si existe. A Pro solo se le rechaza al doble del umbral.
- `/readyz` informa del uso de disco, de las reservas y de la espera por cola, y el panel de administración lo muestra.
~~~~

### P-11 · H-16 · §4.6: copias cada 6 horas, fuera del servidor y con todo lo necesario para restaurar

Sustituye las líneas 215–220 del original, desde «- **Copia diaria:** tarea programada de Coolify, cada día a las 03:15, en el contenedor `apiint`. Ejecuta `python -m app.ops.backup`:» hasta «- `python -m app.ops.restore <archivo>` restaura, y se prueba en la CI con una base vacía.».

~~~~markdown
- **Copia de la base de datos:** tarea programada de Coolify cada 6 horas en el contenedor `apiint`, con tiempo máximo de 3.600 s (el valor por defecto de Coolify es 300 s). Ejecuta `python -m app.ops.backup`:
  - `pg_dump` en formato personalizado a `/srv/backups/postgres/`, con un `postgresql-client` de la misma versión mayor que el servidor (instálalo desde el repositorio de PGDG; `/readyz` comprueba la versión);
  - retención local de `BACKUP_RETENTION_DAYS` días.
- **Copia fuera del servidor**, obligatoria para el cierre operativo de F1: con `BACKUP_RESTIC_REPOSITORY` definido (por ejemplo, SFTP a otro servidor propio), restic envía cada copia y aplica `forget --prune` con 7 diarias, 4 semanales y 6 mensuales. `apiint` sale a ese destino por la red `edge` (12.2). Sin esta copia, perder el VPS es perder la base de datos.
- **Qué más se copia:**
  - el directorio del token PKCS#11 del sello (volumen `softhsm`);
  - un volcado cifrado de las variables del recurso en Coolify y del `.env` de Coolify (`/data/coolify/source/.env`): sin `AUTH_SECRET` no se pueden descifrar las claves JWKS que Better Auth guarda cifradas en la base de datos;
  - la base de datos de Coolify (`pg_dump` del contenedor `coolify-db`) con un cron del host descrito en `docs/OPERATIONS.md`.
- Los archivos de usuario no se copian: son temporales por diseño.
- `python -m app.ops.restore <archivo>` restaura y se prueba en la CI con una base vacía. `docs/OPERATIONS.md` describe la restauración completa en un VPS nuevo, con un objetivo de menos de 4 horas, y un simulacro trimestral.
- Si la copia falla dos veces seguidas, se avisa a `ADMIN_EMAILS`.
~~~~

### P-12 · H-17, H-31, H-32 · §5.1: herramientas híbridas acotadas y autenticación solo por cabecera

Sustituye las líneas 232–238 del original, desde «- **Herramientas «cliente»:** se procesan en el navegador y nunca suben el archivo. Si el archivo supera 100 MB o el dispositivo falla por memoria, la herramienta ofrece la ruta de servidor.» hasta «5. `GET /v1/jobs/{id}` devuelve las salidas con URLs firmadas de `files.{{DOMINIO}}`.».

~~~~markdown
- **Herramientas «cliente»:** se procesan en el navegador y nunca suben el archivo. Si el archivo supera `CLIENT_MAX_MB` (100 MB) o el navegador se queda sin memoria, la herramienta lo dice y sugiere una alternativa; no tienen versión de servidor salvo que sean híbridas.
- **Herramientas «híbridas»:** solo las marcadas `hybrid` en el registro: unir-pdf con Office o TIFF, pdf-a-jpg y pdf-a-png con archivos grandes, imagenes-a-pdf con TIFF o lotes grandes, copiar-de-pdf, comparar-pdf con archivos de más de `CLIENT_MAX_MB`, lector-pdf con archivos que no son PDF y girar-pdf con autoorientación. Su parte de servidor es la que indica su línea del catálogo.
- **Herramientas «servidor»:**
  1. El navegador obtiene identidad: JWT si hay sesión, o `POST /v1/session/anon` con Turnstile, que devuelve un token anónimo firmado válido 24 horas.
  2. Sube por tus a `upload.{{DOMINIO}}` y recibe los `upload_id`.
  3. `POST /v1/jobs` con `{tool, upload_ids, options}`. La API valida plan, cuota y opciones, mueve las entradas y encola en la cola del grupo.
  4. `GET /v1/jobs/{id}/events` (Server-Sent Events, latido cada 15 s porque Cloudflare corta conexiones inactivas) informa del progreso.
  5. `GET /v1/jobs/{id}` devuelve las salidas con URLs firmadas de `files.{{DOMINIO}}`.
- La API autentica solo por la cabecera `Authorization` (JWT o token anónimo), nunca por cookies; así no hay superficie de CSRF.
~~~~

### P-13 · H-17, H-18, H-19, H-28, H-46 · §5.2: clase de coste, separación especificación e implementación, precedencia de flags

Sustituye las líneas 242–258 del original, desde «Cada herramienta es un módulo Python (y, si es de cliente, un módulo TypeScript) inscrito en un registro central con:» hasta «El registro alimenta la API (`/v1/tools`), la generación estática de páginas, el sitemap y los conversores universales.».

~~~~markdown
Cada herramienta es un módulo Python (y, si es de cliente o híbrida, un módulo TypeScript) inscrito en un registro central con:

| Campo | Ejemplo |
| --- | --- |
| `slug_es`, `slug_en` | `comprimir-pdf`, `compress-pdf` |
| `category` | `pdf`, `office`, `image`, `audio`, `video`, `ai`, `data`, `sign`, `invoice` o `3d` |
| `where` | `client`, `server` o `hybrid` (5.1) |
| `worker_group` | `pdf`, `ocr`, `office`, `convert`, `media`, `ai`, `sign`, `av`, `utils`, `mesh`, `cad` |
| `cost_class` | `light`, `heavy` o `ai` (9.3) |
| `inputs` / `outputs` | tipos MIME y extensiones |
| `options_schema` | modelo Pydantic con valores por defecto |
| `limits` | por plan, sobrescriben los generales |
| `ai_requests_estimate` | función que estima peticiones de IA antes de encolar |
| `phase` | F1 a F7 |
| `flag` | `TOOL_<SLUG>_ENABLED` y fila en `feature_flags` |
| `indexable` | si tiene página propia indexable |

- El registro separa la especificación (slugs, opciones, límites y fase) de la implementación: `packages/tools/<grupo>/<slug>/spec.py` no importa motores y `impl.py` solo se importa en los workers. La API y la web cargan solo especificaciones, y una prueba falla si importar el registro carga torch, Docling, OpenCascade o FFmpeg.
- `scripts/export_registry.py` genera `packages/registry/registry.json` con el JSON Schema de cada `options_schema`; la web lo importa al compilar y genera sus tipos con json-schema-to-typescript. La CI falla si el JSON no está al día.
- Precedencia de flags:
  1. `TOOL_<SLUG>_ENABLED=false` en el entorno apaga la herramienta siempre (interruptor de emergencia);
  2. si la variable no está definida, manda la fila de `feature_flags`;
  3. sin fila, la herramienta está activa desde su fase;
  4. los flags temáticos (`HEVC_DECODE_ENABLED`, `INVOICING_ES_ENABLED`, `VIDEO_H264_ENCODING_ENABLED`, `GDRIVE_ENABLED`, `DROPBOX_ENABLED`) se aplican además y solo pueden apagar.
- Una herramienta apagada no tiene página indexable: su URL lleva `noindex` y una explicación, y sale del sitemap (7.22).

El registro alimenta la API (`/v1/tools`), la generación estática de páginas, el sitemap y los conversores universales.
~~~~

### P-14 · H-14, H-35 · §5.3: visibilidad de Valkey, intentos, latidos y secretos cifrados

Sustituye las líneas 262–269 del original, desde «- **Idempotencia** por `(propietario, sha256 de entradas, herramienta, opciones)`: si el resultado sigue en disco, se devuelve sin reprocesar.» hasta «- `acks_late` y `prefetch_multiplier=1`.».

~~~~markdown
- **Idempotencia** por `(propietario, sha256 de entradas, herramienta, opciones sin secretos)`: si el resultado sigue en disco, se devuelve sin reprocesar y la subida duplicada se borra. El índice único de `idempotency_key` es parcial: solo cubre trabajos `queued`, `running` o `succeeded` no caducados.
- **Estados:** `queued`, `running`, `succeeded`, `failed`, `cancelled`, `expired`.
- **Errores** con código estable y mensaje traducido. La lista completa está en `docs/ERRORS.md` e incluye `FILE_TOO_LARGE`, `UNSUPPORTED_FORMAT`, `PASSWORD_REQUIRED`, `INVALID_OPTIONS`, `AI_CONSENT_REQUIRED`, `AI_BUDGET_EXHAUSTED`, `AI_UNAVAILABLE`, `QUEUE_FULL`, `DISK_FULL`, `TIMEOUT` y `WORKER_LOST`.
- **Secretos de los trabajos** (contraseñas de PDF y similares): la API los cifra con AES-GCM y `JOB_SECRETS_KEY`, viajan cifrados en los argumentos de la tarea y el worker los descifra en memoria. Nunca se guardan en claro en Valkey, en la base de datos, en logs ni en la clave de idempotencia.
- **Celery:**
  - `time_limit` y `soft_time_limit` por herramienta;
  - `broker_transport_options.visibility_timeout` mayor que el `time_limit` más largo más 10 minutos: Valkey reentrega las tareas sin confirmar cuando vence ese plazo, y con trabajos de vídeo o transcripción de horas se ejecutarían dos veces;
  - `acks_late`, `prefetch_multiplier=1` y `task_reject_on_worker_lost=False`;
  - cada trabajo en curso actualiza `jobs.heartbeat_at` cada 30 s; beat reencola con un intento nuevo los trabajos `running` sin latido desde hace 3 minutos;
  - cada tarea lleva su número de intento y el worker la descarta si `jobs.attempts` ya es mayor;
  - al tercer intento fallido (por ejemplo, porque el contenedor murió por memoria) el trabajo pasa a `failed` con `WORKER_LOST` y no se reencola;
  - reintentos solo en errores transitorios;
  - prioridad para Pro con las prioridades de Celery sobre Valkey (`priority_steps` y `queue_order_strategy="priority"`);
  - sin backend de resultados (`task_ignore_result`): el estado vive en `jobs`;
  - parada en caliente con `stop_grace_period` igual al `time_limit` del grupo, con un máximo de 10 minutos.
~~~~

### P-15 · H-15, H-30 · §5.4: concurrencia por tamaño de VPS, hilos y memoria

Sustituye las líneas 271–287 del original, desde «### 5.4 Grupos de workers y concurrencia por defecto (8 vCPU)» hasta «Todo configurable con `CONCURRENCY_<GRUPO>`.».

~~~~markdown
### 5.4 Grupos de workers y concurrencia por defecto (8 y 16 vCPU)

| Grupo | Motores principales | Concurrencia (8 / 16 vCPU) | Hilos por trabajo | `mem_limit` (8 / 16 vCPU) |
| --- | --- | --- | --- | --- |
| `pdf` | pikepdf, qpdf, pypdfium2, Pillow | 3 / 6 | 1 | 3 / 6 GB |
| `ocr` | OCRmyPDF, Tesseract, veraPDF | 1 / 2 | 2 | 3 / 6 GB |
| `office` | LibreOffice con unoserver, Calibre, cliente de Gotenberg | 2 / 3 (`light` 1 y `heavy` 1 en 8 vCPU) | 1 | 3 / 4 GB |
| `convert` | Docling (backend pypdfium2) | 1 / 1 | 2 | 5 / 8 GB |
| `media` | imágenes, libros, correo, CAD 2D | 2 / 3 | 1 | 3 / 4 GB |
| `ai` | OpenRouter, fastembed | 4 / 6 | 1 | 2 / 3 GB |
| `sign` | pyHanko | 1 / 1 | 1 | 1 / 1 GB |
| `av` | FFmpeg, faster-whisper, Kokoro | 2 / 3 (`light` 1 y `heavy` 1 en 8 vCPU) | 2 | 3 / 6 GB |
| `utils` | formatos de F6, KoSIT en modo servicio | 2 / 2 | 1 | 3 / 4 GB |
| `mesh` | mallas 3D y G-code | 1 / 2 | 1 | 4 / 6 GB |
| `cad` | OpenCascade, OpenSCAD, LibreDWG | 1 / 1 | 1 | 4 / 6 GB |
| `gotenberg` | LibreOffice y Chromium | 1 instancia | sin cambio | 3 / 4 GB |
| `gotenbergweb` | Chromium | 1 instancia | sin cambio | 1,5 / 2 GB |

- Todo configurable con `CONCURRENCY_<GRUPO>` y `THREADS_<GRUPO>`.
- Fija los hilos de cada motor a `THREADS_<GRUPO>`: OCRmyPDF `--jobs`, `OMP_THREAD_LIMIT`, `OMP_NUM_THREADS`, `torch.set_num_threads`, FFmpeg `-threads` y faster-whisper `cpu_threads`. Por defecto, la mayoría de estos motores usan todos los núcleos, y una veintena de procesos a la vez saturarían el servidor.
- `cpus` de cada contenedor = concurrencia × hilos. `cpu_shares` mayor para `web`, `api`, `apiint`, `upload`, `files` y `workerpdf`, para que las páginas y las herramientas rápidas respondan durante los picos.
- `postgres` lleva `mem_limit` de 2,5 / 4 GB. La suma de los `mem_limit` puede superar la RAM en un 15 % como máximo (unos 36 GB en 32 GB hasta F4 y unos 72 GB en 64 GB con el catálogo completo). `oom_score_adj` de −500 para `postgres`, `valkey`, `web`, `api`, `apiint`, `upload` y `files`, y de +500 para los workers: si se agota la memoria del host, el núcleo mata antes un worker (su trabajo vuelve a la cola, 5.3) que la base de datos.
- `av` y `office` tienen dos colas con procesos separados, `light` (notas de voz, conversiones cortas) y `heavy` (transcripciones, vídeo, hojas de cálculo enormes), para que un trabajo de horas no bloquee los de segundos.
- KoSIT Validator corre como servicio HTTP dentro de `workerutils` (modo daemon), para no arrancar la JVM en cada factura.
- Kokoro va en `av`, que es intensivo en CPU, y no en `ai`, que queda para trabajos de entrada y salida con OpenRouter.
~~~~

### P-16 · H-05, H-06 · §6.1: condiciones de OpenRouter verificadas el 31/10/2026

Sustituye las líneas 295–303 del original, desde «| Condición | Consecuencia en el sistema |» hasta «Documenta en `docs/OPERATIONS.md` los pasos de configuración de la cuenta de OpenRouter (compra única, ajuste de privacidad, clave).».

~~~~markdown
| Condición (comprobada el 31/10/2026; vuelve a comprobarla al empezar F3) | Consecuencia en el sistema |
| --- | --- |
| Modelos gratuitos: 20 peticiones por minuto; 50 al día si la cuenta ha comprado menos de 10 créditos en total y 1.000 al día si ha comprado al menos 10 | Comprar una vez 10 $ es una decisión con coste: pídela (0.1). Limitador propio por debajo de esas cifras |
| El límite es global de la cuenta: más claves o más cuentas no suman | Una sola clave |
| Con saldo negativo puede devolver 402, también en modelos gratuitos | Mantener saldo positivo y avisar en el panel |
| `GET /api/v1/key` devuelve `free_model_daily_requests` (`used`, `limit` y `remaining`) del día UTC | Es la fuente de verdad del consumo diario; el limitador propio se reconcilia con ella |
| La documentación no dice si los intentos fallidos cuentan para el límite diario | Contar cada intento y cada reintento contra el presupuesto |
| Los modelos gratuitos rotan sin aviso | Descubrimiento automático y lista de reserva |
| La política de datos depende del proveedor de cada modelo: unos entrenan con los textos y otros no. La cuenta tiene ajustes separados para modelos gratuitos y de pago, y `provider.data_collection: "deny"` en cada petición limita el enrutado a proveedores que no recogen datos | Cuenta configurada para no permitir proveedores que entrenan ni que publican; todas las peticiones llevan `data_collection: "deny"`; si no queda ningún modelo válido para una herramienta, se desactiva sola (6.2) |

Documenta en `docs/OPERATIONS.md` los pasos de configuración de la cuenta de OpenRouter: compra única, ajustes de privacidad que no permiten entrenar ni publicar, y clave.
~~~~

### P-17 · H-05, H-06 · §6.2: descubrimiento con tokens de salida y enrutado sin recogida de datos

Sustituye las líneas 307–318 del original, desde «- Al arrancar y cada `LLM_MODELS_REFRESH_HOURS` horas, `GET {OPENROUTER_BASE_URL}/models`. Filtra los modelos cuyo id termina en `:free`.» hasta «- El panel de administración muestra la lista, permite desactivar un modelo y fijar preferencias.».

~~~~markdown
- Al arrancar y cada `LLM_MODELS_REFRESH_HOURS` horas, `GET {OPENROUTER_BASE_URL}/models`. Guarda los modelos con precio 0 en entrada y en salida, lleven o no el sufijo `:free`.
- Guarda en `llm_models`:
  - `context_length` y `max_completion_tokens`;
  - si admite `response_format` o salidas estructuradas;
  - si admite imagen de entrada;
  - fecha de última vez visto.
- Orden de preferencia:
  1. `LLM_PREFERRED_MODELS` (lista ordenada; puede estar vacía);
  2. los descubiertos, ordenados por tasa de éxito propia de los últimos 7 días y después por contexto.
- Cada petición envía `models` con hasta 3 candidatos que cumplan los requisitos de la tarea (contexto, tokens de salida, JSON y visión) y `provider: {"data_collection": "deny"}`. OpenRouter pasa al siguiente si uno falla o está saturado; la respuesta indica el modelo usado y se registra.
- Último recurso: el enrutador `openrouter/free` (`LLM_FALLBACK_ROUTER`), también con `data_collection: "deny"`.
- Un modelo que falla porque ningún proveedor cumple `data_collection: "deny"` queda desactivado 24 horas (`disabled_until`).
- Si ningún modelo cumple los requisitos de una herramienta, esa herramienta se muestra «no disponible temporalmente» (`AI_UNAVAILABLE`) sin gastar peticiones.
- El panel de administración muestra la lista, permite desactivar un modelo y fijar preferencias.
~~~~

### P-18 · H-06 · §6.3: presupuesto reconciliado, tope por tarea y bloques según la salida del modelo

Sustituye las líneas 322–351 del original, desde «Limitador global en Valkey, atómico (script Lua):» hasta «| transcribir-audio, video-a-subtitulos, pdf-a-audio, imagen-a-texto | 0 (local) |».

~~~~markdown
Limitador global en Valkey, atómico (script Lua):

| Parámetro | Valor por defecto |
| --- | --- |
| `AI_RPM_LIMIT` | 18 por minuto (ventana deslizante) |
| `AI_DAILY_BUDGET` | 950 al día (margen de 50 sobre el límite) |
| `AI_PRO_RESERVE` | 400 peticiones diarias reservadas para Pro |
| `AI_CHAT_RPM_SHARE` | 0,5: el chat usa como máximo la mitad del límite por minuto |
| `AI_TASK_MAX_REQUESTS` | 20 peticiones por tarea |
| `AI_BUDGET_RESET_TZ` | `UTC` (reinicio a las 00:00 UTC, como el contador de OpenRouter) |

- **Antes de encolar**, la herramienta estima sus peticiones (`ai_requests_estimate`). La API las reserva contra estos límites:
  1. la cuota diaria del usuario y el máximo por tarea (9.3);
  2. el presupuesto global (sin tocar la reserva Pro si el usuario no es Pro);
  3. el límite por minuto.
- **Si no hay presupuesto**, error `AI_BUDGET_EXHAUSTED` con la hora de reinicio en hora de Madrid.
- **Las reservas no usadas** se devuelven al terminar el trabajo.
- **Cada petición real**, incluidos los fallos y los reintentos, cuenta y se registra en `ai_requests`: modelo, tokens, latencia y estado, nunca el contenido.
- **Errores 429 o 5xx de OpenRouter:** espera exponencial respetando `Retry-After` y como máximo 2 reintentos, que cuentan contra el presupuesto.
- **Reconciliación:** cada 10 minutos, `GET {OPENROUTER_BASE_URL}/key`. Si `free_model_daily_requests.used` es mayor que el contador propio, el contador sube a ese valor; si `remaining` baja de 20, solo Pro puede usar IA. El saldo se muestra en el panel de administración.
- **Tamaño de bloque:** el texto de cada petición se trocea según el contexto y el `max_completion_tokens` del modelo elegido, porque una traducción ocupa a la salida tanto como a la entrada. Nunca por un número fijo de caracteres.
- Coste estimado por herramienta:

| Herramienta | Peticiones |
| --- | --- |
| resumir-pdf | 1 si cabe en el contexto; si no, 1 por bloque + 1 final |
| chat-pdf | 1 por mensaje |
| generador-de-preguntas, pdf-a-fichas, ticket-a-excel | 1 |
| pdf-a-presentacion | 2 |
| traducir-pdf, traducir-word/excel/powerpoint | 1 por bloque, con bloques que quepan en la salida máxima del modelo |
| manuscrito-a-texto | 1 por página (máximo 10) |
| resumir-reunion, traducir-subtitulos | 1 por bloque de transcripción |
| transcribir-audio, video-a-subtitulos, pdf-a-audio, imagen-a-texto | 0 (local) |

- Si una tarea necesitaría más de `AI_TASK_MAX_REQUESTS`, la API lo dice antes de encolar y ofrece procesar un rango de páginas.
- Las herramientas de IA se anuncian como «beta, sujeta a disponibilidad diaria», y su página muestra cuántas peticiones quedan hoy (`GET /v1/ai/budget`).
~~~~

### P-19 · H-04, H-25 · §6.4: embeddings admitidos, voz sin GPL en proceso y modelo de quitar fondo

Sustituye las líneas 355–359 del original, desde «- **Embeddings:** fastembed con un modelo multilingüe pequeño cuya licencia permita uso comercial (por ejemplo `intfloat/multilingual-e5-small`; verifícalo). Vectores en pgvector con la dimensión del modelo.» hasta «- **Extracción de texto:** pypdfium2 y Docling.».

~~~~markdown
- **Embeddings:** fastembed con `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (Apache-2.0, 384 dimensiones), que fastembed admite de serie; `intfloat/multilingual-e5-small` no está en su lista de modelos. Vectores en pgvector con la dimensión del modelo.
- **Transcripción:** faster-whisper en CPU, modelo `small` con `int8` por defecto y `medium` opcional.
- **Voz:** Kokoro (pesos Apache-2.0) con voces en español e inglés.
  - Los fonemas se obtienen ejecutando `espeak-ng` como proceso externo (GPL) y se pasan a Kokoro. No instales `misaki[en]` ni `phonemizer-fork`: son GPL y se cargarían dentro del proceso de Python.
  - Kokoro no publica versión desde abril de 2025; fija la versión y anota el riesgo de mantenimiento en `docs/DECISIONS.md`.
  - La calidad en español la valida el propietario con una escucha antes de activar pdf-a-audio en español.
  - Texto troceado por frases y salida MP3 con FFmpeg.
- **Quitar fondo:** rembg con `REMBG_MODEL=isnet-general-use` o `u2net`, tras verificar la licencia de sus pesos. Nunca `bria-rmbg`, que es el modelo por defecto de rembg y cuyo uso comercial exige un acuerdo de pago con BRIA.
- **OCR:** Tesseract.
- **Extracción de texto:** pypdfium2; si el PDF es escaneado, OCR en `workerocr`; estructura y tablas con Docling solo en `workerconvert`. El resultado se guarda en `document_texts` y `workerai` lo reutiliza sin cargar Docling.
~~~~

### P-20 · H-34 · §6.5: caché de IA por propietario

Sustituye la línea 368 del original: «- Caché por `(sha256, herramienta, opciones, idioma)` con la misma caducidad que los archivos del usuario. Repetir una tarea no gasta.».

~~~~markdown
- Caché por `(propietario, sha256, herramienta, opciones, idioma)` con la misma caducidad que los archivos del usuario. Repetir una tarea no gasta. No se comparte entre usuarios: hacerlo revelaría si otra persona ha procesado el mismo documento.
~~~~

### P-21 · H-05, H-47 · §6.6: aviso fiel a la política real y enrutado sin recogida de datos

Sustituye las líneas 373–379 del original, desde «- Antes de la primera tarea de IA de cada sesión, la interfaz muestra este aviso con casilla obligatoria:» hasta «- Proveedor falso determinista cuando `OPENROUTER_API_KEY` está vacío y `APP_ENV=development`.».

~~~~markdown
- Antes de la primera tarea de IA de cada sesión, la interfaz muestra este aviso con casilla obligatoria:
  > «Para esta herramienta, el texto de tu documento se envía a un proveedor de IA externo a través de OpenRouter, que puede estar fuera de la Unión Europea. Solo usamos proveedores que declaran no entrenar con los datos, pero pueden conservarlos un tiempo según su política. No la uses con documentos confidenciales ni con datos personales de terceros.»
- Sin consentimiento, la API devuelve 400 (`AI_CONSENT_REQUIRED`). `AI_REQUIRE_CONSENT` está a `true` y no puede desactivarse en producción. Cada consentimiento se guarda en `ai_consents` con la fecha y la versión del texto.
- Nunca se envía a OpenRouter contenido de las herramientas de firma, verificación de firmas, contactos, calendario, correo o certificados. Esas herramientas no tienen opción de IA.
- `provider.data_collection: "deny"` va en todas las peticiones y no se puede cambiar en producción.
- La política de privacidad lista a OpenRouter y a sus proveedores como destinatarios, explica la posible transferencia fuera de la UE y enlaza a sus políticas. Añade en `docs/LEGAL.md` que debe revisarlo un especialista en protección de datos, junto con una evaluación de impacto (EIPD) del tratamiento con IA.
- Interfaz `LLMProvider` para cambiar en el futuro a modelos de pago con retención cero sin tocar las herramientas.
- Proveedor falso determinista cuando `OPENROUTER_API_KEY` está vacío y `APP_ENV=development`.
~~~~

### P-22 · H-12, H-52 · §7.1: slug rellenar-pdf y redacción por rasterizado por defecto

Sustituye las líneas 391–395 del original, desde «- unir-pdf, dividir-pdf, girar-pdf, eliminar-paginas-pdf, extraer-paginas-pdf, organizar-pdf — `@cantoo/pdf-lib` — F1» hasta «- escaner-pdf — cámara, OpenCV.js y pdf-lib, usable como PWA — F2».

~~~~markdown
- unir-pdf, dividir-pdf, girar-pdf, eliminar-paginas-pdf, extraer-paginas-pdf, organizar-pdf — `@cantoo/pdf-lib` — F1
- numerar-paginas-pdf, marca-de-agua-pdf, recortar-pdf (CropBox) — `@cantoo/pdf-lib` — F1
- cambiar-tamano-pagina-pdf, varias-paginas-por-hoja, folleto-pdf (imposición para imprimir) — `@cantoo/pdf-lib` con `embedPage` — F1
- lector-pdf, anotar-pdf, editar-pdf (añadir texto, imágenes y formas; no reescribir párrafos), rellenar-pdf, aplanar-pdf — EmbedPDF — F1
- redactar-pdf — EmbedPDF y PDFium; por defecto rasteriza las zonas afectadas (A.6) — F1
- escaner-pdf — cámara, OpenCV.js y pdf-lib, usable como PWA — F2
~~~~

### P-23 · H-22 · §7.2: HEIC y vídeo HEVC detrás del mismo flag

Sustituye las líneas 399–405 del original, desde «- pdf-a-jpg, pdf-a-png — PDFium en navegador; pypdfium2 en servidor si el archivo es grande — F1» hasta «- pdf-a-tiff (multipágina), pdf-a-webp — pypdfium2 y Pillow — F2; pdf-a-svg — pdftocairo — F2».

~~~~markdown
- pdf-a-jpg, pdf-a-png — PDFium en navegador; pypdfium2 en servidor si el archivo es grande — F1
- jpg-a-pdf, png-a-pdf, webp-a-pdf, gif-a-pdf, bmp-a-pdf — navegador (canvas y pdf-lib) — F1
- tiff-a-pdf (img2pdf, sin recomprimir), svg-a-pdf (Chromium de `gotenberg`), heic-a-pdf — servidor — F2
  - Para HEIC usa libheif compilado solo para decodificar, con libde265 y sin x265.
  - No uses los wheels de pillow-heif: incluyen x265 y quedan bajo GPLv2.
  - Todo lo HEVC (HEIC y vídeo H.265) va detrás de `HEVC_DECODE_ENABLED`, apagado por defecto. PDF24 rechaza HEIC por el riesgo de patentes de HEVC, y el programa HEVC Advance cobra por usuario a los servicios en la nube que usan decodificadores HEVC. Actívalo solo tras la revisión que documentes en `docs/LEGAL.md`. Mientras esté apagado, la página explica cómo exportar a JPEG desde el móvil y lleva `noindex`.
- pdf-a-tiff (multipágina), pdf-a-webp — pypdfium2 y Pillow — F2; pdf-a-svg — pdftocairo — F2
~~~~

### P-24 · H-04, H-08, H-38 · §7.3: convertir-a-pdf, Gotenberg sin red, documentos enlazados y motores sin trampas de licencia

Sustituye las líneas 409–416 del original, desde «- word-a-pdf, excel-a-pdf, ppt-a-pdf (aceptan también doc, xls, ppt y pps), odt-a-pdf, ods-a-pdf, odp-a-pdf, rtf-a-pdf, txt-a-pdf, csv-a-pdf — Gotenberg con LibreOffice — F1» hasta «- dxf-a-pdf — ezdxf — F2».

~~~~markdown
- convertir-a-pdf — página general que acepta todos los formatos de esta sección y elige el motor — F1
- word-a-pdf, excel-a-pdf, ppt-a-pdf (aceptan también doc, xls, ppt y pps), odt-a-pdf, ods-a-pdf, odp-a-pdf, rtf-a-pdf, txt-a-pdf, csv-a-pdf — Gotenberg con LibreOffice — F1
- html-a-pdf y markdown-a-pdf — Chromium de `gotenberg`, sin red: se aceptan HTML suelto o un ZIP con sus recursos, y los recursos remotos no se cargan (la página lo explica) — F1
- web-a-pdf — Chromium de `gotenbergweb`, por `egressweb`; si la URL apunta a un documento convertible (por ejemplo, un DOCX o una imagen), `workeroffice` lo descarga por `egressweb` con los límites del plan y lo convierte como si se hubiera subido — F1
- pages-a-pdf, keynote-a-pdf, numbers-a-pdf, visio-a-pdf, publisher-a-pdf — LibreOffice (importación parcial; avisar de la calidad) — F2
- epub-a-pdf, mobi-a-pdf, azw3-a-pdf, fb2-a-pdf — Calibre — F2
- cbz-a-pdf, cbr-a-pdf — libarchive, Pillow y pikepdf — F2
- djvu-a-pdf — ddjvu — F2
- eml-a-pdf, msg-a-pdf — `email` de la biblioteca estándar y mail-parser para EML; olefile y compressed-rtf para MSG (no uses extract-msg, que es GPL); HTML saneado y Chromium de `gotenberg`; cabeceras, cuerpo y adjuntos convertibles como páginas siguientes — F2
- dxf-a-pdf — ezdxf con su backend SVG y Chromium de `gotenberg` para pasar a PDF; nunca el backend PyMuPDF ni el extra `ezdxf[draw]`, que instalan PyMuPDF (AGPL) — F2
~~~~

### P-25 · H-20, H-21 · §7.4: expectativas de Docling y LibreOffice para formatos no PDF

Sustituye las líneas 420–423 del original, desde «- pdf-a-word, pdf-a-excel, pdf-a-ppt — Docling con python-docx, openpyxl y python-pptx, detrás de una interfaz `ConversionProvider` — F2» hasta «- pdf-a-epub — Docling a HTML y pandoc — F2».

~~~~markdown
- pdf-a-word, pdf-a-excel, pdf-a-ppt — Docling (backend pypdfium2) con python-docx, openpyxl y python-pptx, detrás de una interfaz `ConversionProvider` — F2
  - El resultado es editable y se recompone el flujo del texto; no es una copia exacta del diseño. La página lo dice y ofrece el modo «Fiel al diseño» (A.9), que usa la importación de PDF de LibreOffice en `workeroffice`.
  - Límite de páginas por plan (9.3) y tiempo máximo por página; si se supera, se ofrece procesar un rango.
- pdf-a-odt, pdf-a-ods, pdf-a-odp, pdf-a-rtf — salida anterior convertida con LibreOffice (unoserver) en `workeroffice`, porque Gotenberg solo produce PDF — F2
- pdf-a-txt (pypdfium2), pdf-a-markdown y pdf-a-html (Docling), pdf-a-csv y pdf-a-json (tablas con Docling) — F2
- pdf-a-epub — Docling a HTML y pandoc con `--sandbox` — F2
~~~~

### P-26 · H-38, H-39, H-41 · §7.5: OCRmyPDF sin Ghostscript, escala de grises segura, eliminar-metadatos y comparar en el navegador

Sustituye las líneas 427–439 del original, desde «- comprimir-pdf — pikepdf y Pillow (recompresión y reducción de imágenes por niveles) más el optimizador de OCRmyPDF — F1» hasta «- pdf-a-factura-electronica (Factur-X / ZUGFeRD) — XML CII y PDF/A-3; detalle y resto de herramientas de factura en 7.23 — F4».

~~~~markdown
- comprimir-pdf — pikepdf y Pillow (recompresión y reducción de imágenes por niveles) más el optimizador de OCRmyPDF — F1
- ocr-pdf, pdf-a-pdfa — OCRmyPDF 17 con rasterizador pypdfium2 y `--pdfa-backend internal` (nunca usa Ghostscript), Tesseract y validación con veraPDF. Si un PDF no se puede convertir a PDF/A sin Ghostscript, la tarea falla con un informe claro y ofrece rasterizar las páginas con capa de texto OCR — F2
- pikepdf, qpdf y pypdfium2 — F2:
  - proteger-pdf (AES-256);
  - desbloquear-pdf (solo con la contraseña del usuario, nunca forzando);
  - reparar-pdf;
  - optimizar-pdf-web (linealizar);
  - pdf-escala-de-grises (reescribiendo los operadores de color de los flujos de contenido, de modo que texto y vectores siguen siendo vectoriales, y pasando a gris imágenes, degradados y anotaciones; las páginas con construcciones que no sepa convertir con seguridad, como sombreados por función o espacios DeviceN, se rasterizan en gris y se avisa);
  - extraer-imagenes-pdf;
  - metadatos-pdf (ver y editar) y eliminar-metadatos-pdf (página propia, como en PDF24, que quita todo y muestra antes lo que va a borrar).
- comparar-pdf — híbrida: texto con PDFium y diff-match-patch, y diferencias visuales por página, en el navegador; en servidor solo si algún archivo supera `CLIENT_MAX_MB` — F2
- word-a-pdf-accesible — Gotenberg con `pdfua` y validación con veraPDF — F4
- pdf-a-factura-electronica (Factur-X / ZUGFeRD) — XML CII y PDF/A-3; detalle y resto de herramientas de factura en 7.23 — F4
~~~~

### P-27 · H-06, H-15 · §7.6: grupos de imagen-a-texto y pdf-a-audio

Sustituye las líneas 443–450 del original, desde «- chat-pdf, resumir-pdf, generador-de-preguntas, traducir-pdf — F3» hasta «- pdf-a-audio (Kokoro local) — F3».

~~~~markdown
- chat-pdf, resumir-pdf, generador-de-preguntas, traducir-pdf — F3
  - traducir-pdf regenera DOCX y PDF con maquetación simplificada, detrás de una interfaz `TranslationProvider`. No uses BabelDOC (AGPL).
- imagen-a-texto (Tesseract, local, grupo `ocr`) — F3
- imagen-a-excel (OCR, Docling y, si hace falta, LLM) — F3
- ticket-a-excel (LLM con salida estructurada) — F3
- pdf-a-presentacion (LLM y python-pptx) — F3
- pdf-a-fichas (LLM) — F3
- pdf-a-audio (Kokoro local, grupo `av`, con límite de caracteres por plan en 9.3) — F3
~~~~

### P-28 · H-22 · §7.9: remultiplexar antes de recodificar y flags de códecs

Sustituye las líneas 476–477 del original, desde «- mp4-a-webm, webm-a-mp4, mov-a-mp4, mkv-a-mp4, avi-a-mp4, video-a-gif, gif-a-mp4 — FFmpeg — F5» hasta «- comprimir-video, recortar-video, rotar-video, quitar-audio-video — FFmpeg — F5».

~~~~markdown
- mp4-a-webm, webm-a-mp4, mov-a-mp4, mkv-a-mp4, avi-a-mp4, video-a-gif, gif-a-mp4 — FFmpeg — F5
  - Si los códecs de entrada caben en el contenedor de salida (por ejemplo, H.264 y AAC de un MOV o un MKV a MP4), se remultiplexa con `-c copy`: tarda segundos y no codifica nada.
  - Solo se recodifica a H.264 con `VIDEO_H264_ENCODING_ENABLED` activo; si está apagado, el MP4 de salida usa AV1 y la página lo indica.
  - Las entradas HEVC (vídeos de iPhone) necesitan `HEVC_DECODE_ENABLED` salvo que solo se remultipliquen; si no se puede, la página lo explica.
- comprimir-video, recortar-video, rotar-video, quitar-audio-video — FFmpeg, sin recodificar cuando el corte y la operación lo permiten — F5
~~~~

### P-29 · H-04, H-22, H-39 · §7.11: SVG en el navegador, flag HEVC y modelo de rembg

Sustituye las líneas 486–491 del original, desde «- png-a-jpg, jpg-a-png, webp-a-jpg, webp-a-png, jpg-a-webp, png-a-webp, avif-a-jpg, jpg-a-avif, gif-a-png, bmp-a-jpg, tiff-a-jpg, png-a-ico y convertir-imagen (cualquier combinación) — jSquash y canvas en el navegador — F5» hasta «- raw-a-jpg (CR2, NEF, ARW y DNG con LibRaw), psd-a-png (psd-tools), svg-a-png (resvg), png-a-svg y jpg-a-svg (vectorizar con vtracer) — servidor — F5».

~~~~markdown
- png-a-jpg, jpg-a-png, webp-a-jpg, webp-a-png, jpg-a-webp, png-a-webp, avif-a-jpg, jpg-a-avif, gif-a-png, bmp-a-jpg, tiff-a-jpg, png-a-ico y convertir-imagen (cualquier combinación) — jSquash y canvas en el navegador — F5
- heic-a-jpg, heic-a-png — servidor, con la misma decodificación y el mismo flag `HEVC_DECODE_ENABLED` que heic-a-pdf — F5
- svg-a-png, svg-a-jpg — `@resvg/resvg-wasm` en el navegador, sin cargar recursos externos — F5
- comprimir-imagen, redimensionar-imagen, crear-favicon, quitar-metadatos-foto (EXIF y GPS), imagen-a-base64, leer-codigo-qr (zxing-cpp en WebAssembly) — navegador — F5
- quitar-fondo — rembg con el modelo de 6.4 — F5
- raw-a-jpg (CR2, NEF, ARW y DNG con LibRaw mediante rawpy), psd-a-png (psd-tools), png-a-svg y jpg-a-svg (vectorizar con vtracer) — servidor — F5
~~~~

### P-30 · H-02 · §7.12: pandoc siempre con --sandbox

Sustituye la línea 495 del original: «- docx-a-odt, odt-a-docx, docx-a-markdown, markdown-a-docx, docx-a-html, html-a-docx — pandoc — F6».

~~~~markdown
- docx-a-odt, odt-a-docx, docx-a-markdown, markdown-a-docx, docx-a-html, html-a-docx — pandoc siempre con `--sandbox`, que le impide leer archivos que no sean la entrada y acceder a la red — F6
~~~~

### P-31 · H-20 · §7.12: pptx-a-imagenes por Gotenberg

Sustituye la línea 499 del original: «- pptx-a-imagenes — LibreOffice y pypdfium2 — F6; pptx-a-video — diapositivas renderizadas y FFmpeg — F6».

~~~~markdown
- pptx-a-imagenes — Gotenberg a PDF y pypdfium2 — F6; pptx-a-video — diapositivas renderizadas y FFmpeg — F6
~~~~

### P-32 · H-10 · §7.14: motores de verificación de firmas

Sustituye las líneas 511–516 del original, desde «- csig-a-pdf, p7m-a-pdf, xsig-a-pdf (extraer el documento original firmado) — asn1crypto, cryptography y defusedxml — F6» hasta «- facturae-a-pdf, ubl-a-pdf, cii-a-pdf — validación con el XSD oficial, plantilla HTML y Chromium — F6».

~~~~markdown
- csig-a-pdf, p7m-a-pdf, xsig-a-pdf (extraer el documento original firmado; si no es un PDF, se entrega tal cual y se ofrece convertirlo) — asn1crypto, cryptography y defusedxml — F6
- verificar-firma — pyHanko para CAdES y PAdES, con su validación AdES y sus listas de confianza de la UE, y signxml para XAdES — F6
  - Admite .csig, .xsig, .p7m y PDF firmados.
  - Muestra firmante, fecha, validez de la cadena y si el documento cambió.
  - La parte de PDF se adelanta a F4 como verificar-firmas-pdf (sección 7.23), con lista de confianza de la UE y revocación.
- facturae-a-pdf, ubl-a-pdf, cii-a-pdf — validación con el XSD oficial, plantilla HTML y Chromium de `gotenberg` — F6
~~~~

### P-33 · H-02, H-04, H-08, H-39 · §7.17: draw.io GPL externo, mermaid en el navegador, LaTeX aislado y captura por gotenbergweb

Sustituye las líneas 531–536 del original, desde «- drawio-a-pdf, drawio-a-png — draw.io desktop en modo exportación sin interfaz — F6» hasta «- captura-web (URL a PNG o JPG) — Gotenberg con Chromium, por el proxy de salida — F6».

~~~~markdown
- drawio-a-pdf, drawio-a-png — draw.io desktop (GPL-3.0, proceso externo) en modo exportación con `xvfb-run`, sin red y con tiempo máximo — F6
- mermaid-a-png, mermaid-a-svg — mermaid en el navegador — F6
- latex-a-pdf — Tectonic sin shell-escape, sin red (con el paquete de TeX precargado en la imagen y el modo sin descargas de la versión fijada), como proceso con entorno vacío y con el aislamiento de 12.1 — F6
- midi-a-mp3, midi-a-wav — FluidSynth con un banco de sonidos cuya licencia permita uso comercial (verifícala y regístrala) — F6
- musicxml-a-pdf, midi-a-pdf (partitura) — MuseScore (GPL, externo, sin interfaz) — F6
- captura-web (URL a PNG o JPG) — Chromium de `gotenbergweb`, por `egressweb` — F6
~~~~

### P-34 · H-04 · §7.19: dwg-a-pdf sin PyMuPDF

Sustituye la línea 561 del original: «- dwg-a-dxf, dwg-a-pdf — LibreDWG (GPL, externo); calidad irregular, avisar al usuario — F7».

~~~~markdown
- dwg-a-dxf, dwg-a-pdf — LibreDWG (GPL, externo) para pasar a DXF y la ruta de dxf-a-pdf (7.3) para el PDF; calidad irregular, avisar al usuario — F7
~~~~

### P-35 · H-39, H-53 · §7.20: comprimir-glb y render-modelo-3d en el navegador

Sustituye la línea 570 del original: «- comprimir-glb (Draco) y render-modelo-3d (miniatura PNG con three.js en Chromium sin interfaz) — F7».

~~~~markdown
- comprimir-glb (Draco, con glTF Transform y draco3d) y render-modelo-3d (miniatura PNG con three.js) — navegador — F7
~~~~

### P-36 · H-18 · §7.22: reglas de indexación del catálogo

Sustituye las líneas 591–594 del original, desde «- conversor-pdf — página que elige la ruta según formatos de entrada y salida — F1, y crece en cada fase» hasta «- Las combinaciones sin página propia llevan `noindex`, para no crear cientos de páginas casi iguales.».

~~~~markdown
- conversor-pdf — página que elige la ruta según formatos de entrada y salida — F1, y crece en cada fase
- convertir-archivo y convertir-modelo-3d — F5 y F7
  - Son conversores universales: detectan el tipo por bytes y ofrecen solo las salidas posibles.
  - Las combinaciones sin página propia no tienen URL indexable: se resuelven dentro del conversor universal, y un enlace compartido con parámetros lleva `noindex`.
- Reglas de indexación para todo el catálogo:
  - Una página se indexa solo cuando su herramienta está activa, ha pasado sus pruebas y su contenido propio (8.2) está completo en ese idioma; hasta entonces lleva `noindex` y no está en el sitemap.
  - Las páginas alias (por ejemplo, pub-a-pdf) llevan `canonical` a la principal.
~~~~

### P-37 · H-10, H-11, H-43 · §7.23 Facturas: flag común, firma en el navegador, escenarios de KoSIT y aviso legal actualizado

Sustituye las líneas 612–635 del original, desde «**Facturas (grupo utils)**» hasta «- Mientras tanto, la página avisa de que no sustituye a un software de facturación.».

~~~~markdown
**Facturas (grupo utils)**

Las herramientas que generan facturas (crear-factura, crear-factura-electronica y pdf-a-factura-electronica) van detrás de `INVOICING_ES_ENABLED`, apagado por defecto, además de su flag propio. Las que validan o muestran facturas (validar-factura-electronica y factura-electronica-a-pdf) no generan facturas y pueden activarse antes.

- crear-factura — página de elección y diseñador visual de facturas PDF en el navegador, con plantillas propias, IVA, recargo de equivalencia y retención de IRPF — F4
- crear-factura-electronica — F4
  - Formulario EN 16931 con validación en vivo.
  - Salidas: Factur-X/ZUGFeRD, XRechnung (CII o UBL), Peppol BIS Billing 3.0, UBL 2.1 y Facturae 3.2.2.
  - Facturae puede llevar firma XAdES-EPES con la política de firma de Facturae, hecha en el navegador con xadesjs y el certificado del usuario o de su empresa (.p12 o .pfx abierto con PKI.js). La clave privada nunca sale del navegador.
  - CII con drafthorse; incrustación con factur-x, o con los campos Factur-X de Gotenberg (`facturxXml` y siguientes) cuando el PDF se genera desde HTML.
- pdf-a-factura-electronica — F4
  - Si el PDF ya trae XML, lo reutiliza.
  - Si no, extrae los datos en este orden: texto, reglas y una sola petición de LLM con salida estructurada, con consentimiento.
  - La revisión en formulario es obligatoria: nada se genera sin que el usuario confirme.
  - Conserva las páginas originales.
- factura-electronica-a-pdf — F6
  - Amplía cii-a-pdf, ubl-a-pdf y facturae-a-pdf (7.14).
  - Salida PDF/A-3 con el XML original incrustado sin modificar un byte.
  - Admite lotes.
- validar-factura-electronica — F4
  - Motor: KoSIT Validator (Java, Apache-2.0, como programa externo en modo servicio) con las configuraciones públicas de XRechnung (`validator-configuration-xrechnung`) y Peppol BIS (`validator-configuration-bis`).
  - Para EN 16931 sin CIUS y para Factur-X/ZUGFeRD no hay configuración pública: crea escenarios propios con los artefactos oficiales (Schematron de EN 16931 de la Comisión Europea, con licencia EUPL-1.2, y Schematron de Factur-X/ZUGFeRD) y anota sus licencias en `docs/LICENSES.md`.
  - KoSIT 1.6 solo recibe mantenimiento: anota en `docs/DECISIONS.md` la alternativa si deja de publicarse.
  - Facturae: XSD y verificación de la firma con signxml.
- **Aviso legal.** Anótalo en `docs/LEGAL.md` para revisarlo con un asesor antes de activar `INVOICING_ES_ENABLED`:
  - Un generador de facturas usado por empresas o autónomos españoles es un sistema informático de facturación (Reglamento Veri*factu, RD 1007/2023). Los productores de estos sistemas deben cumplirlo desde el 29/7/2025; los usuarios están obligados desde el 1/1/2027 (sociedades) y el 1/7/2027 (resto), según el RDL 15/2025.
  - La factura electrónica obligatoria entre empresas (RD 238/2026 y Orden HAC/1028/2026, en vigor desde el 6/10/2026) obliga a emitir por plataformas de intercambio o por la solución pública de la AEAT, y a enviar a esta una copia en UBL. Estas herramientas no son una plataforma de intercambio: generan, convierten y validan formatos.
  - Mientras tanto, las páginas avisan de que no sustituyen a un software de facturación.
~~~~

### P-38 · H-08, H-10 · §7.23 verificar-firmas-pdf: listas de confianza con pyHanko y salida por egressweb

Sustituye las líneas 666–667 del original, desde «- pyHanko y pyhanko-certvalidator.» hasta «- Lista de confianza de la UE (LOTL y listas nacionales), descargada por el proxy de salida y cacheada.».

~~~~markdown
  - pyHanko (validación AdES, análisis de diferencias y listas de confianza de la UE) con pyhanko-certvalidator.
  - Lista de confianza de la UE (LOTL y listas nacionales), descargada por `egressweb` y cacheada; pyHanko comprueba la firma de la LOTL contra el ancla publicada en el Diario Oficial de la UE.
~~~~

### P-39 · H-18, H-52 · §7.23 pub-a-pdf con canonical

Sustituye la línea 674 del original: «- pub-a-pdf — alias de publisher-a-pdf — F2».

~~~~markdown
- pub-a-pdf — alias de publisher-a-pdf, con `canonical` a esa página — F2
~~~~

### P-40 · H-18, H-33, H-51, H-54 · §8.2: correo sin abuso, Drive y Dropbox reales, contenido propio medible y datos estructurados vigentes

Sustituye las líneas 743–753 del original, desde «4. Progreso, resultado, descarga y «Seguir con otra herramienta» con el mismo archivo. Además:» hasta «6. Datos estructurados `SoftwareApplication` y `FAQPage`, imagen Open Graph generada por herramienta, `hreflang`, `canonical` y sitemap por idioma.».

~~~~markdown
4. Progreso, resultado, descarga y «Seguir con otra herramienta» con el mismo archivo. Además:
   - **Enviar por correo**, solo para usuarios registrados:
     - se envía un enlace firmado que caduca a las 24 horas, nunca el archivo adjunto;
     - plan gratuito: solo a su propia dirección verificada; Pro: hasta 3 destinatarios por envío;
     - límite diario `MAIL_SHARE_DAILY_LIMIT`, Turnstile y enlace «Informar de abuso» en cada correo;
     - el dominio de `MAIL_FROM` tiene SPF, DKIM y DMARC.
   - **Guardar en Google Drive o Dropbox:**
     - Google Drive: el navegador descarga el resultado y lo sube con la API de Drive y el ámbito `drive.file`;
     - Dropbox: el componente Saver recibe la URL firmada y son los servidores de Dropbox quienes descargan el archivo, así que esa URL dura 15 minutos y el WAF no debe bloquearlos;
     - ninguna credencial pasa por el servidor;
     - los scripts de Google y de Dropbox se cargan solo al pulsar el botón, nunca al cargar la página;
     - cada uno va detrás de su flag (`GDRIVE_ENABLED`, `DROPBOX_ENABLED`).
   - **Abrir desde Google Drive o Dropbox** en la zona de subida, con los mismos flags.
5. Contenido propio de cada página, en cada idioma: qué hace, pasos, preguntas frecuentes, límites por plan, formatos de entrada y salida y herramientas relacionadas.
   - Orientativo: 300 palabras propias por página. Ningún párrafo se repite literalmente en más de 3 páginas; una prueba de la CI lo comprueba.
   - Lo redactas tú a partir del registro, la sección 7 y el Anexo A, sin inventar cifras ni funciones. El propietario lo revisa por muestreo antes de quitar el `noindex` (7.22).
   - Valoración de 1 a 5 e «Informar de un problema» (tabla `tool_feedback`). Solo se muestran valoraciones reales, nunca inventadas.
6. Datos estructurados `SoftwareApplication` (con `offers` a precio 0, y `aggregateRating` solo cuando haya al menos 5 valoraciones reales) y `BreadcrumbList`. Google retiró en 2026 los resultados enriquecidos de preguntas frecuentes, así que `FAQPage` no aporta. Imagen Open Graph generada por herramienta, `hreflang` con `x-default`, `canonical` y sitemap por idioma.
~~~~

### P-41 · H-29, H-31, H-47 · §9.1: chat sin salida directa de la API, estado de subidas, webhook idempotente y exportación

Sustituye las líneas 769–783 del original, desde «| Método y ruta | Descripción |» hasta «| `GET /healthz`, `/readyz` | Vida y preparación (base de datos, Valkey, disco, Gotenberg) |».

~~~~markdown
| Método y ruta | Descripción |
| --- | --- |
| `GET /v1/tools` | Catálogo, límites por plan y flags |
| `POST /v1/session/anon` | Verifica Turnstile y emite un token anónimo firmado válido 24 horas, con límite de emisiones por IP (12.4) |
| `GET /v1/uploads/{id}` | Estado de una subida (`ready` o `rejected`) |
| `POST /v1/jobs` | Crea trabajo: `{tool, upload_ids, options, ai_consent?}` |
| `GET /v1/jobs/{id}` | Estado, progreso, salidas con URL firmada y caducidad, error |
| `GET /v1/jobs/{id}/events` | Server-Sent Events con latido |
| `DELETE /v1/jobs/{id}` | Borra el trabajo y sus archivos ya |
| `GET /v1/me`, `/v1/me/usage`, `/v1/me/jobs` | Datos del usuario |
| `GET /v1/me/export` | Exportación de los datos de la cuenta (RGPD) |
| `POST /v1/shares` | Crea enlace para compartir |
| `POST /v1/ai/chat` | Mensaje de chat sobre un documento ya procesado. La API no sale a internet: encola en `workerai` y retransmite por Server-Sent Events los fragmentos que este publica en Valkey |
| `GET /v1/ai/budget` | Peticiones de IA restantes para el usuario y disponibilidad global |
| `POST /v1/billing/checkout`, `/v1/billing/portal`, `/v1/billing/webhook` | Stripe. El webhook verifica la firma sobre el cuerpo sin modificar y es idempotente por `event.id` (tabla `stripe_events`) |
| `/v1/signature-requests`, `/v1/sign/{token}` | Solicitar firmas (F4) |
| `GET /healthz`, `/readyz` | Vida y preparación (base de datos, Valkey, disco, reservas, colas, Gotenberg y versión de `pg_dump`) |
~~~~

### P-42 · H-06, H-19, H-23, H-31 · §9.3: cuotas por clase de coste, archivos por tarea y límites de IA alcanzables

Sustituye las líneas 795–806 del original, desde «| Límite | Anónimo | Gratis registrado | Pro |» hasta «| Prioridad de cola | baja | normal | alta |».

~~~~markdown
| Límite | Anónimo | Gratis registrado | Pro |
| --- | --- | --- | --- |
| Tareas ligeras de servidor al día (`cost_class=light`: comprimir, Office a PDF, proteger, audio corto y similares) | 20 | 50 | 1.000 (uso justo) |
| Tareas pesadas de servidor al día (`heavy`: OCR, PDF a Office, transcripción, vídeo, CAD y similares) | 2 | 10 | 200 |
| Archivos por tarea | 5 | 20 | 100 |
| Tamaño máximo por archivo | 50 MB | 100 MB | 1 GB |
| Tamaño total por tarea | 100 MB | 300 MB | 2 GB |
| Páginas por PDF | 100 | 300 | 2.000 |
| Duración de audio | 10 min | 30 min | 4 h |
| Vídeo | No | No | Sí, hasta 1 h y 1 GB |
| Triángulos por malla | 1 millón | 2 millones | 10 millones |
| Peticiones de IA al día | 0 | 3 | 30 |
| Peticiones de IA por tarea | — | 5 | 20 (`AI_TASK_MAX_REQUESTS`) |
| Páginas por tarea de IA | — | 30 | 150 |
| Caracteres por tarea de pdf-a-audio | — | 20.000 | 300.000 |
| Retención de archivos | 1 h | 24 h | 24 h; compartir hasta 7 días |
| Prioridad de cola | baja | normal | alta |

- Los límites viven en la tabla `plans`, sembrada por una migración desde `config/plans.yaml`; no hay variables de entorno que los dupliquen.
- Una tarea es un `POST /v1/jobs` con todos sus archivos. Un resultado servido por idempotencia no cuenta, y las herramientas de navegador no cuentan nunca.
- Las cuotas anónimas se cuentan por token y por IP (por /64 en IPv6); manda la más restrictiva.
- «Uso justo» en Pro: por encima de 1.000 tareas ligeras al día, el trabajo pasa a prioridad normal y se avisa al administrador.
- Los límites de IA son máximos, no garantías: dependen del presupuesto global de 6.3, y la página muestra lo que queda hoy.
~~~~

### P-43 · H-09, H-26, H-34 · §9.4: tablas que faltaban, propiedad de las migraciones y cachés por propietario

Sustituye las líneas 810–833 del original, desde «| Tabla | Columnas clave |» hasta «Todo contenido derivado de documentos de usuario (`document_texts`, `document_chunks`, `ai_cache`) caduca con los archivos y lo borra Celery beat.».

~~~~markdown
| Tabla | Columnas clave |
| --- | --- |
| tablas de Better Auth | usuarios (con `role`, `banned` y demás campos del plugin de administración), sesiones, cuentas, verificaciones y `jwks`; las crea `migrateauth` con la CLI de Better Auth |
| `profiles` | `user_id`, `plan_id`, `locale`, `created_at` (el rol vive en la tabla de usuarios de Better Auth) |
| `plans` | `id`, `name`, `limits` (jsonb) |
| `subscriptions` | `user_id`, `stripe_customer_id`, `stripe_subscription_id`, `status`, `current_period_end` |
| `stripe_events` | `id` (id del evento de Stripe), `type`, `received_at`, `processed_at` |
| `anon_clients` | `id`, `token_hash`, `ip_hash`, `created_at`, `expires_at` |
| `uploads` | `id` (id de tus), `owner_type`, `owner_id`, `path`, `size`, `sha256`, `detected_mime`, `original_name`, `state` (`uploading`, `ready`, `rejected` o `consumed`), `created_at`, `expires_at` |
| `jobs` | `id`, `owner_type`, `owner_id`, `tool`, `options` (sin secretos), `status`, `progress`, `worker_group`, `priority`, `idempotency_key` (único parcial, 5.3), `attempts`, `heartbeat_at`, `ai_reserved`, `ai_used`, `error_code`, `created_at`, `started_at`, `finished_at`, `expires_at`, `cpu_seconds` |
| `job_inputs` / `job_outputs` | `job_id`, `name`, `path`, `size`, `mime`, `sha256` |
| `usage_daily` | `owner_type`, `owner_id`, `date`, `cost_class`, `tasks`, `ai_requests`, `mail_shares` |
| `ai_requests` | `id`, `owner_type`, `owner_id`, `tool`, `model`, `prompt_tokens`, `completion_tokens`, `status`, `latency_ms`, `created_at` (sin contenido) |
| `ai_consents` | `owner_type`, `owner_id`, `text_version`, `created_at` |
| `llm_models` | `id`, `context_length`, `max_completion_tokens`, `supports_json`, `supports_images`, `enabled`, `disabled_until`, `priority`, `success_rate_7d`, `last_seen_at` |
| `document_texts` | `owner_type`, `owner_id`, `sha256`, `pages` (jsonb), `extractor`, `expires_at` |
| `document_chunks` | `id`, `owner_type`, `owner_id`, `sha256`, `page`, `chunk_index`, `text`, `embedding` (vector), `expires_at` |
| `ai_cache` | `key` (incluye el propietario), `result` (jsonb), `expires_at` |
| `shares` | `id`, `job_output_id`, `token_hash`, `expires_at`, `downloads`, `revoked_at` |
| `tool_feedback` | `id`, `tool`, `rating`, `message`, `owner_type`, `owner_id`, `created_at` (sin archivos) |
| `user_tool_prefs` | `user_id`, `favorites`, `recent` (jsonb) |
| `signature_requests` | `id`, `owner_id`, `job_output_id`, `status`, `created_at`, `expires_at` |
| `signers` | `id`, `request_id`, `email`, `name`, `sign_order`, `token_hash`, `code_hash`, `status`, `signed_at` |
| `audit_events` | `id`, `request_id`, `event`, `actor`, `ip_hash`, `user_agent`, `document_sha256`, `created_at`; alimenta el certificado de auditoría de solicitar-firmas |
| `seal_signatures` | `id`, `job_id`, `document_sha256`, `level`, `created_at`; registra cada uso del sello de la plataforma |
| `feature_flags` | `slug`, `enabled`, `plans` |
| `audit_log` | `actor`, `action`, `target`, `created_at`; acciones de administración |

- Todo contenido derivado de documentos de usuario (`document_texts`, `document_chunks`, `ai_cache`) pertenece a un solo propietario, caduca con sus archivos y lo borra Celery beat. Las cachés no se comparten entre usuarios.
- Alembic gestiona todas las tablas salvo las de Better Auth, que crea `migrateauth`; `migrate` se ejecuta después.
- Los workers usan un rol de PostgreSQL (`SERVICE_PASSWORD_WORKERDB`) con permisos solo sobre `jobs`, `job_inputs`, `job_outputs`, `usage_daily`, `ai_requests`, `document_texts`, `document_chunks`, `ai_cache`, `llm_models` y `seal_signatures`.
~~~~

### P-44 · H-09 · §10: custodia del sello, límites y certificado del usuario solo en el navegador

Sustituye las líneas 839–844 del original, desde «- Certificado de la plataforma por PKCS#11. En desarrollo, uno autofirmado generado por script. Nunca en el repositorio.» hasta «- muestra el nivel que detecta verificar-firmas-pdf sobre el resultado.».

~~~~markdown
- Sello de la plataforma:
  - certificado y clave por PKCS#11 (SoftHSM2 en el VPS, salvo que el propietario aporte un HSM); en desarrollo, uno autofirmado generado por script; nunca en el repositorio;
  - solo `workersign` monta el token (volumen `softhsm`) y conoce `SIGN_PKCS11_PIN`; `workersign` no ejecuta otros motores que pyHanko y tiene el aislamiento de 12.1;
  - cada uso se registra en `seal_signatures` con el sha256 del documento; `SEAL_DAILY_LIMIT` limita los sellos diarios y `SEAL_ENABLED=false` lo apaga al instante;
  - con un token software no hay dispositivo cualificado de creación de sellos, así que el sello no es cualificado y no se anuncia como tal.
- Sello de tiempo RFC 3161 con `TSA_URL`. La TSA de producción la elige el propietario (0.1), porque puede tener coste y ser o no cualificada.
- La interfaz explica que la firma dibujada es simple y que el sello acredita la integridad del documento y el momento, no la identidad del firmante. Añade en `docs/LEGAL.md` que los niveles eIDAS que se prometan deben revisarse con un especialista.
- Certificado propio del usuario o de su empresa: solo con firma interrumpida (A.6). La clave nunca llega al servidor, y el servidor nunca guarda certificados con clave privada.
  - La interfaz no promete «avanzada» ni «cualificada» de antemano.
  - Muestra el nivel que detecta verificar-firmas-pdf sobre el resultado.
~~~~

### P-45 · H-03, H-04, H-22 · §11: lista de licencias aplicable, trampas conocidas y códecs coherentes

Sustituye las líneas 850–872 del original, desde «- **Frontend** (se distribuye al navegador): solo MIT, Apache-2.0, BSD o MPL-2.0.» hasta «- SBOM CycloneDX en cada compilación.».

~~~~markdown
- **Política en un fichero:** `scripts/license_policy.yaml` contiene las listas de esta sección y es lo que aplica la CI.
- **Frontend** (se distribuye al navegador): MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD, MPL-2.0, Zlib, Unlicense, CC0-1.0, BlueOak-1.0.0, CC-BY-4.0 (solo datos, como caniuse-lite) y OFL-1.1 (solo fuentes). En licencias dobles se elige la permisiva (por ejemplo, node-forge con BSD-3-Clause).
- **Backend:** lo anterior más PSF-2.0, Python-2.0, HPND y MIT-CMU (Pillow), LGPL-2.1, LGPL-3.0, EPL-2.0, EUPL-1.2 (solo datos) y LicenseRef-TOST-1.0 (usd-core).
- **GPL**, solo como programa externo en servidor, invocado por línea de órdenes y nunca importado: la CI falla si un paquete de Python o de npm instalado es GPL o AGPL. Los programas GPL permitidos son los de la sección 2.
- **Prohibido enlazar o empaquetar AGPL:** Ghostscript, MuPDF, PyMuPDF, pdf2docx, BabelDOC, EbookLib, Documenso, DocuSeal, PrusaSlicer, OrcaSlicer, Bambu Studio, CuraEngine, UVtools, libbgcode, MinIO, Garage, xmlsig y similares.
- **Trampas conocidas:**
  - `ezdxf[draw]` instala PyMuPDF: instala `ezdxf` sin ese extra y usa su backend SVG;
  - el paquete `ocrmypdf` de las distribuciones depende de Ghostscript: instala OCRmyPDF con pip;
  - extract-msg es GPL: para MSG usa olefile y compressed-rtf;
  - `misaki[en]` y `phonemizer-fork` son GPL: espeak-ng solo como programa externo;
  - los wheels de pillow-heif incluyen x265 (GPLv2);
  - el modelo por defecto de rembg (`bria-rmbg`) exige un acuerdo de pago para uso comercial.
- **Impresión 3D:** permitidos lib3mf (BSD-2-Clause), trimesh, assimp, manifold3d, usd-core (TOST-1.0) y OpenCascade (LGPL con excepción).
- **Paridad con PDF24** (comprueba cada licencia al añadirla):
  - Frontend: qr-code-styling, Konva, TipTap (solo paquetes MIT del registro público de npm; Pages y la conversión a DOCX de TipTap son de pago y no se usan), `docx`, mammoth, KaTeX, PKI.js, xadesjs, mermaid, `@resvg/resvg-wasm`, glTF Transform y SheetJS Community Edition (Apache-2.0, instalada desde cdn.sheetjs.com con versión fijada, porque la del registro de npm, 0.18.5, tiene vulnerabilidades sin corregir; Renovate no la vigila, así que revísala a mano en cada fase).
  - Backend: img2pdf (LGPL), drafthorse (Apache-2.0), factur-x (BSD), signxml (Apache-2.0), olefile (BSD) y unoserver (MIT).
  - Como programas externos: KoSIT Validator (Java, Apache-2.0), unpaper (GPL, lo invoca OCRmyPDF), pngquant (GPL), jbig2enc (Apache-2.0), tiffcp de libtiff, draw.io desktop (GPL-3.0) y espeak-ng (GPL-3.0).
  - Las reglas Schematron de EN 16931 (EUPL-1.2), XRechnung y Peppol se usan como datos en servidor y se registran en `docs/LICENSES.md` con la licencia que publique cada una.
- **FFmpeg:**
  - preferir compilación LGPL;
  - una compilación GPL (con x264) solo como programa externo en servidor;
  - nunca `libfdk_aac`;
  - nunca ffmpeg.wasm en el frontend: `@ffmpeg/core` es GPL-2.0-or-later.
- **Códecs:**
  - riesgo bajo: MP3, Opus, Vorbis y FLAC;
  - AAC (codificador nativo de FFmpeg), VP9 y AV1: sus autores los publican libres de regalías o con licencias de patentes propias, pero hay pools que reclaman licencias; anota la revisión en `docs/LEGAL.md`;
  - codificación H.264 tras `VIDEO_H264_ENCODING_ENABLED`, apagado hasta la revisión legal;
  - decodificación HEVC (vídeo H.265 y HEIC) tras `HEVC_DECODE_ENABLED`, apagado hasta la revisión legal;
  - documenta en `docs/LEGAL.md` que el uso comercial de H.264 y HEVC puede requerir licencia de patentes, también como servicio en la nube.
- **Modelos y recursos:** comprueba y registra la licencia de los modelos de Whisper, Kokoro, embeddings, rembg y Docling (código MIT; modelos con Apache-2.0 o CDLA-Permissive-2.0 según la ficha de cada uno; no uses modelos sin ficha de licencia) y del banco de sonidos de FluidSynth.
- **CI:**
  - `scripts/check_licenses.py` (pip-licenses y license-checker de npm) aplica `scripts/license_policy.yaml` y falla ante una licencia fuera de lista, una licencia desconocida o un paquete GPL o AGPL;
  - `scripts/check_images.sh` falla si alguna imagen contiene `gs`, `mutool` o PyMuPDF;
  - SBOM CycloneDX en cada compilación.
~~~~

### P-46 · H-02, H-15 · §12.1: secretos mínimos por contenedor y motores con entorno vacío

Sustituye las líneas 880–881 del original, desde «- Usuario sin privilegios, `read_only` con tmpfs pequeño en `/tmp` (los archivos grandes van a `jobs/<id>/work`), `cap_drop: [ALL]`, `no-new-privileges`, `pids_limit`, `mem_limit` y `cpus` por servicio.» hasta «- Runtime configurable con `WORKER_RUNTIME`: `runsc` (gVisor) si está instalado en el host, `runc` por defecto.».

~~~~markdown
- Usuario sin privilegios, `read_only` con tmpfs pequeño en `/tmp` (los archivos grandes van a `jobs/<id>/work`, y `TMPDIR` y `HOME` apuntan ahí en cada trabajo), `cap_drop: [ALL]`, `no-new-privileges`, `pids_limit`, `mem_limit`, `memswap_limit` y `cpus` por servicio (5.4).
- Runtime configurable con `WORKER_RUNTIME`: `runsc` (gVisor) si está instalado en el host, `runc` por defecto. Comprueba en el primer despliegue que Coolify conserva la clave `runtime`; si no, anota el riesgo aceptado en `docs/SECURITY.md`.
- Secretos mínimos por contenedor, con la matriz en `docs/SECURITY.md`. Cada contenedor comprueba al arrancar que no ve variables que no le tocan; si las ve, no pasa `/readyz`.
  - Los workers que procesan archivos solo reciben `VALKEY_URL`, `DATABASE_URL_WORKER` (rol limitado de 9.4) y, si su grupo maneja contraseñas, `JOB_SECRETS_KEY`.
  - `OPENROUTER_API_KEY` solo en `workerai`; `SIGN_PKCS11_PIN` solo en `workersign`.
  - `FILE_TOKEN_SECRET`, `ANON_TOKEN_SECRET`, `AUTH_SECRET` y las claves de Stripe, SMTP, Google y Dropbox nunca llegan a un worker.
- Cada motor externo (LibreOffice, Calibre, pandoc, Tectonic, OpenSCAD, MuseScore, draw.io, FFmpeg, readpst, LibreDWG, ddjvu, pdftocairo, espeak-ng) se ejecuta como subproceso con entorno vacío salvo `PATH`, `HOME` y `TMPDIR` del trabajo, con el directorio del trabajo como directorio actual y con tiempo y memoria limitados (`prlimit`).
- El proceso del worker se marca como no volcable (`PR_SET_DUMPABLE=0`), para que un subproceso no pueda leer su `/proc/<pid>/environ`.
~~~~

### P-47 · H-08 · §12.2: mapa de redes y salidas, dos proxies y dos Gotenberg

Sustituye las líneas 885–891 del original, desde «- Red interna (`internal: true`) sin salida a internet para workers, gotenberg, valkey, postgres, apiint, upload y files.» hasta «- Tras el primer despliegue, revisa la vista *Deployable Compose* de Coolify y confirma que se conservan `runtime`, `read_only`, `cap_drop`, límites y redes internas. Si alguna clave se pierde, aplica una alternativa y documéntala en `docs/DEPLOY.md`.».

~~~~markdown
- Redes de Compose:
  - `internal` (`internal: true`, sin salida a internet): todos los servicios;
  - `edge` (con salida): solo `web`, `api`, `apiint`, `beat`, `egressai` y `egressweb`;
  - `webrender` (`internal: true`): `gotenbergweb`, `egressweb`, `workeroffice` y `workersign`;
  - `airelay` (`internal: true`): `workerai` y `egressai`;
  - Coolify añade su red para el proxy en los servicios con dominio (`web`, `api`, `upload`, `files` y `umami`).
- Qué sale y por dónde:
  - `web`: Google OAuth y SMTP;
  - `api`: verificación de Turnstile, API de Stripe y SMTP;
  - `apiint` y `beat`: SMTP de avisos y repositorio remoto de restic;
  - `workerai`: OpenRouter, solo por `egressai`;
  - `gotenbergweb` (web-a-pdf y captura-web), `workeroffice` (documentos enlazados de web-a-pdf) y `workersign` (TSA, OCSP, CRL y lista de confianza de la UE): solo por `egressweb`;
  - el resto, nada.
- Smokescreen identifica a sus clientes por certificado TLS. Para no montar mTLS hay dos instancias, cada una con su política:
  - `egressai`: modo `enforce` con OpenRouter como único dominio permitido;
  - `egressweb`: cualquier host público; deniega IP privadas, de enlace local, de metadatos de la nube y de las redes de Docker (`--deny-range` para 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 100.64.0.0/10, 169.254.0.0/16, fc00::/7 y fe80::/10).
- La API solo acepta en web-a-pdf y captura-web URL `http` o `https` con puerto 80 o 443.
- Gotenberg (desde la 8.32 los filtros de salida vienen desactivados por defecto):
  - `gotenberg`, que recibe archivos de usuarios, no tiene salida: además de estar solo en la red `internal`, lleva `--chromium-deny-public-ips=true`, `--chromium-deny-private-ips=true`, `--libreoffice-deny-public-ips=true` y `--libreoffice-deny-private-ips=true`;
  - `gotenbergweb` usa `--chromium-proxy-server=http://egressweb:4750` y nunca recibe archivos de usuarios;
  - en los dos, `downloadFrom` y los webhooks quedan bloqueados (`--api-download-from-deny-public-ips`, `--api-download-from-deny-private-ips`, `--webhook-deny-public-ips` y `--webhook-deny-private-ips` a `true`).
- Tras el primer despliegue, revisa la vista *Deployable Compose* de Coolify y confirma que se conservan `runtime`, `read_only`, `cap_drop`, límites y redes internas. Una prueba de humo en el VPS intenta salir a internet desde cada worker y desde `gotenberg`, y debe fallar. Si alguna clave se pierde, aplica una alternativa y documéntala en `docs/DEPLOY.md`.
~~~~

### P-48 · H-02 · §12.3: bombas de píxeles, SVG, ZIP de Office y entradas que leen archivos

Sustituye las líneas 895–914 del original, desde «- Tipo real por bytes; límites de tamaño, páginas, duración y triángulos comprobados antes de procesar.» hasta «- límites estrictos de tiempo y memoria.».

~~~~markdown
- Tipo real por bytes; límites de tamaño, páginas, duración, píxeles y triángulos comprobados antes de procesar.
- Protección frente a bombas de descompresión:
  - imágenes: `IMAGE_MAX_PIXELS` (100 megapíxeles) comprobado en la cabecera antes de decodificar, y el mismo valor en `Image.MAX_IMAGE_PIXELS` de Pillow;
  - PDF: al rasterizar, ninguna página pasa de `RENDER_MAX_PIXELS` (50 megapíxeles; la resolución baja para respetarlo), con tiempo máximo por página;
  - comprimidos: ver abajo.
- Contraseñas de PDF solo en memoria (5.3).
- LibreOffice sin macros y sin recursos enlazados (Gotenberg 8.34 o posterior los descarta; en `workeroffice`, la misma política y sin red). Chromium sin acceso a `file://` fuera del directorio de la petición.
- FFmpeg:
  - `-nostdin` y `-protocol_whitelist file,pipe`;
  - lista blanca de formatos de entrada, sin listas HLS, concat ni playlists, que pueden leer archivos locales o URLs;
  - `ffprobe` previo;
  - límites de duración y de tiempo de proceso.
- XML (Facturae, UBL, CII, XAdES, KML, GPX, 3MF, AMF, DAE, X3D, draw.io, MusicXML) siempre con defusedxml, sin entidades externas.
- SVG: en el navegador, resvg sin recursos externos; en servidor (svg-a-pdf y svg-a-stl), solo imágenes en `data:` y ninguna referencia a archivos ni URL.
- Comprimidos y contenedores ZIP (3MF, KMZ, DOCX, XLSX, PPTX, ODT, EPUB y .gcode.3mf). Rechaza:
  - rutas con `..` o absolutas;
  - enlaces simbólicos;
  - más de 10.000 entradas;
  - más de 2 GB descomprimidos en total, o una relación de compresión mayor de 100:1 en una entrada;
  - en documentos de Office, más de 500 MB descomprimidos.
- Entradas que son código o que referencian archivos (pandoc, OpenSCAD, LaTeX, draw.io y Calibre):
  - sin red;
  - pandoc siempre con `--sandbox`;
  - OpenSCAD: un análisis previo rechaza `include`, `use`, `import` y `surface` con rutas absolutas o con `..`;
  - Tectonic sin shell-escape;
  - Calibre sin archivos locales fuera del directorio del trabajo en la entrada HTML;
  - entorno vacío y límites estrictos de tiempo y memoria (12.1);
  - los mensajes de error de los motores no se devuelven literalmente al usuario;
  - una prueba por motor (16.4) intenta leer `/etc/hostname` y el entorno del proceso padre y comprueba que el resultado no contiene secretos.
~~~~

### P-49 · H-07, H-31, H-32, H-35 · §12.4: IP real solo desde Cloudflare, cabeceras de la web y webhooks

Sustituye las líneas 918–922 del original, desde «- Rate limiting en API y tusd por IP y por usuario; Turnstile para anónimos; CORS restringido a `{{DOMINIO}}`.» hasta «- Renovate, Trivy en la CI y reconstrucción de imágenes ante parches de seguridad de Ghostscript, LibreOffice, PDFium, FFmpeg, Chromium o Tesseract.».

~~~~markdown
- Rate limiting en la API y en los ganchos de tusd por IP y por usuario. La IP real sale de `CF-Connecting-IP` solo cuando la petición llega desde los rangos de Cloudflare (Traefik con `forwardedHeaders.trustedIPs`); en IPv6 se agrupa por /64.
- `POST /v1/session/anon`: Turnstile y como máximo `ANON_TOKENS_PER_IP_DAY` tokens por IP al día.
- CORS de la API restringido a `https://{{DOMINIO}}`; la API autentica solo por la cabecera `Authorization`.
- Cabeceras de la web: `Strict-Transport-Security` con `includeSubDomains`; `Content-Security-Policy` con nonce por petición (`script-src 'self' 'nonce-<valor>' 'wasm-unsafe-eval'`, `worker-src 'self' blob:`, y los dominios de Turnstile, Google y Dropbox solo en las páginas que los usan); `frame-ancestors 'none'`; `Referrer-Policy: strict-origin-when-cross-origin`; y `Permissions-Policy` que solo permite la cámara en escaner-pdf, crear-collage, crear-tarjeta y firmar-pdf.
- Tokens de descarga firmados y con caducidad corta; enlaces de compartir con el token guardado solo como hash.
- Logs sin nombres de archivo ni contenido: solo sha256, tamaño, herramienta, duración y código de error. Los argumentos de las tareas de Celery no se registran.
- Secretos solo por variables de entorno generadas por Coolify; nunca en el repositorio ni en logs.
- Webhooks de Stripe: verificación de firma sobre el cuerpo sin modificar, idempotencia por `event.id` y comprobación de que el WAF y la protección contra bots de Cloudflare no los bloquean.
- Renovate, Trivy en la CI y reconstrucción de imágenes ante parches de seguridad de LibreOffice, PDFium, FFmpeg, Chromium, Tesseract, libheif o FreeType.
~~~~

### P-50 · H-47 · §12.5: bases jurídicas, plazos, subencargados completos y EIPD

Sustituye las líneas 926–929 del original, desde «- Archivos en el VPS (UE), borrado automático aplicado por Celery beat y plazos publicados en la política de privacidad.» hasta «- Exportación y borrado de cuenta desde `/cuenta`.».

~~~~markdown
- Bases jurídicas: ejecución del servicio pedido para procesar archivos (art. 6.1.b del RGPD), consentimiento para las herramientas de IA (6.6) e interés legítimo para seguridad y antiabuso. Regístralas en el registro de actividades de tratamiento de `docs/LEGAL.md`.
- Archivos en el VPS (UE), borrado automático aplicado por Celery beat y plazos publicados en la política de privacidad. `anon_clients`, `ai_requests`, `usage_daily` y los logs se conservan 90 días; `audit_events` y `seal_signatures`, el plazo que fije el asesor.
- Lista de subencargados: proveedor del VPS, Cloudflare, OpenRouter y sus proveedores de modelos, Stripe, proveedor de correo, Sentry si se activa, y Google y Dropbox cuando el usuario los usa. Para cada uno, el país y la garantía de transferencia (marco de privacidad UE-EE. UU., cláusulas tipo u otra).
- Evaluación de impacto (EIPD) del uso de IA con modelos de terceros en `docs/LEGAL.md`, para revisarla con un especialista.
- Analítica sin cookies; sin banner de consentimiento salvo que se añadan cookies no esenciales. La sesión y Turnstile se tratan como estrictamente necesarias, y los scripts de Google y Dropbox solo se cargan cuando el usuario los pide.
- Exportación (`GET /v1/me/export`) y borrado de cuenta desde `/cuenta`.
~~~~

### P-51 · H-07, H-30 · §13.1: cortafuegos del proveedor, certificado de origen y panel cerrado

Sustituye las líneas 937–946 del original, desde «1. Instalar el sistema, crear usuario con clave SSH, desactivar acceso por contraseña y configurar el cortafuegos (22, 80 y 443).» hasta «6. Si el reto HTTP de Let's Encrypt falla detrás de Cloudflare, usar certificados de origen de Cloudflare o reto DNS. Documéntalo.».

~~~~markdown
1. Instalar el sistema, crear usuario con clave SSH y desactivar el acceso por contraseña.
2. Cortafuegos del proveedor (o reglas en `DOCKER-USER`) según 3.1: 22 desde las IP de administración, 80 y 443 desde los rangos de Cloudflare, y nada más.
3. Montar el disco dedicado en `/srv/{{PRODUCTO}}`, si existe.
4. Instalar Coolify con su script oficial y la versión estable fijada.
5. Opcional: instalar gVisor y registrar `runsc` en Docker.
6. En Cloudflare:
   - DNS proxied para `{{DOMINIO}}`, `api`, `upload`, `files` y `stats`;
   - SSL en modo Full (strict) con un certificado de origen de Cloudflare instalado en el proxy de Coolify, y Authenticated Origin Pulls activado si el proxy de Coolify lo admite;
   - WAF básico, comprobando que la protección contra bots no bloquea los webhooks de Stripe;
   - regla de caché para las páginas HTML de herramientas cuando no hay cookie de sesión, con purga en cada despliegue;
   - widget de Turnstile.
7. Panel de Coolify con su dominio a través del proxy y Cloudflare Access; después, cierra 8000, 6001 y 6002.
~~~~

### P-52 · H-16, H-26, H-49, H-50 · §13.2: variables mágicas vigentes, migraciones de un solo uso y tareas programadas

Sustituye las líneas 950–968 del original, desde «- Proyecto `{{PRODUCTO}}`, entorno `production`, recurso Docker Compose desde el repositorio de GitHub, apuntando a `docker-compose.coolify.yml`.» hasta «- Tarea programada de Coolify: copia diaria en `apiint` (sección 4.6).».

~~~~markdown
- Proyecto `{{PRODUCTO}}`, entorno `production`, recurso Docker Compose desde el repositorio de GitHub, apuntando a `docker-compose.coolify.yml`.
- Dominios mediante variables mágicas de Coolify, sin `ports:`. `SERVICE_URL_<ID>_<PUERTO>` incluye el esquema y `SERVICE_FQDN_<ID>_<PUERTO>` es solo el dominio; usa la primera para las URL públicas:
  - `SERVICE_URL_WEB_3000`
  - `SERVICE_URL_API_8000`
  - `SERVICE_URL_UPLOAD_8080`
  - `SERVICE_URL_FILES_8090`
  - `SERVICE_URL_UMAMI_3000` (opcional)
- Nombres de servicio sin guiones ni guiones bajos en los que tienen dominio (Coolify convierte guiones y puntos en guiones bajos dentro de la variable).
- Secretos con variables mágicas, que Coolify genera y conserva entre despliegues:
  - `SERVICE_USER_POSTGRES`, `SERVICE_PASSWORD_POSTGRES`
  - `SERVICE_PASSWORD_VALKEY`
  - `SERVICE_PASSWORD_64_AUTH`
  - `SERVICE_PASSWORD_64_FILES`
  - `SERVICE_PASSWORD_64_ANON`
  - `SERVICE_PASSWORD_64_JOBSECRETS`
  - `SERVICE_PASSWORD_WORKERDB` (rol de PostgreSQL limitado de 9.4)
- El resto de variables con `${VAR:?}` para que Coolify las pida, o con valor por defecto (sección 14). Cada servicio declara en `environment:` solo las variables que le tocan (12.1).
- `healthcheck` en todos los servicios de larga duración. `migrateauth` y `migrate` llevan `exclude_from_hc: true` y `restart: "no"`; los servicios que dependen de ellos usan `depends_on` con `condition: service_completed_successfully`, y el resto, `service_healthy`.
- Volúmenes: `filestore` (`/srv/files`), `backups` (`/srv/backups`), `softhsm` (en `workersign`, y en `apiint` solo para la copia), y datos de `postgres`, `valkey` y `umami`.
- Rotación de logs con `logging: driver json-file` y `max-size: 10m`, `max-file: 5` en cada servicio.
- Tarea programada de Coolify: copia en `apiint` cada 6 horas, con tiempo máximo de 3.600 s (4.6). La actualización de los rangos de Cloudflare y la copia de Coolify van en cron del host, descritas en `docs/OPERATIONS.md`.
- Un despliegue de Compose recrea los contenedores: los workers paran en caliente (5.3) y `docs/DEPLOY.md` indica que los despliegues se hacen en horas valle.
~~~~

### P-53 · H-01, H-48 · §13.3: paso a producción de los pagos y lista del cierre operativo

Sustituye la línea 983 del original: «10. Qué hacer si se llena el disco o se agota el presupuesto de IA.».

~~~~markdown
10. Qué hacer si se llena el disco o se agota el presupuesto de IA.
11. Paso a producción de los pagos: alta en la ventanilla única de IVA (OSS) si se vende a consumidores de otros países de la UE, registros fiscales en Stripe Tax, claves en vivo, precios definitivos y términos y política de reembolsos revisados.
12. Lista de comprobación del cierre operativo de cada fase (`docs/DEPLOY-CHECKLIST.md`).
~~~~

### P-54 · H-06, H-08, H-09, H-14, H-22, H-23, H-25, H-27, H-30, H-31, H-35 · §14: variables que faltaban, renombradas y eliminadas

Sustituye las líneas 989–1064 del original, desde «| Variable | Por defecto | Descripción |» hasta «`.env.example` con todas ellas y valores de desarrollo.».

~~~~markdown
| Variable | Por defecto | Descripción |
| --- | --- | --- |
| `APP_ENV` | `production` | `development` activa proveedores falsos |
| `APP_NAME` | `{{PRODUCTO}}` | Nombre visible |
| `PUBLIC_WEB_URL` | `https://{{DOMINIO}}` | URL de la web |
| `PUBLIC_API_URL` | `https://api.{{DOMINIO}}` | URL de la API |
| `PUBLIC_UPLOAD_URL` | `https://upload.{{DOMINIO}}/files/` | Punto de subida tus |
| `PUBLIC_FILES_URL` | `https://files.{{DOMINIO}}` | Descargas |
| `DEFAULT_LOCALE` | `es` | Idioma por defecto |
| `DISPLAY_TZ` | `Europe/Madrid` | Zona para mostrar horas |
| `DATABASE_URL` | compuesta con las variables mágicas | PostgreSQL |
| `VALKEY_URL` | compuesta con las variables mágicas | Valkey |
| `DATABASE_URL_WORKER` | compuesta con `SERVICE_PASSWORD_WORKERDB` | Rol de PostgreSQL limitado de los workers (9.4) |
| `AUTH_SECRET` | `${SERVICE_PASSWORD_64_AUTH}` | Better Auth |
| `AUTH_JWKS_URL` | `http://web:3000/api/auth/jwks` | JWKS para la API |
| `FILE_TOKEN_SECRET` | `${SERVICE_PASSWORD_64_FILES}` | Firma de descargas |
| `ANON_TOKEN_SECRET` | `${SERVICE_PASSWORD_64_ANON}` | Firma de tokens anónimos |
| `BETTER_AUTH_URL` | `https://{{DOMINIO}}` | URL base de Better Auth |
| `JOB_SECRETS_KEY` | `${SERVICE_PASSWORD_64_JOBSECRETS}` | Cifrado de contraseñas en las tareas (5.3) |
| `FILESTORE_PATH` | `/srv/files` | Raíz del almacenamiento |
| `DISK_MAX_USAGE_PERCENT` | `85` | Guarda de disco |
| `DISK_MIN_FREE_GB` | `20` | Guarda de disco |
| `DISK_RESERVE_FACTOR` | `3` | Reserva de disco por subida (4.5) |
| `QUEUE_MAX_WAIT_SECONDS_<GRUPO>` | `300` (`pdf`: `120`) | Guarda de colas (4.5) |
| `CLIENT_MAX_MB` | `100` | Tamaño máximo en herramientas de navegador (5.1) |
| `FILE_TTL_ANON_MINUTES` | `60` | Retención anónimos |
| `FILE_TTL_USER_HOURS` | `24` | Retención registrados |
| `SHARE_MAX_DAYS` | `7` | Caducidad máxima al compartir |
| `UPLOAD_MAX_BYTES` | `1073741824` | Máximo absoluto (Pro) |
| `UPLOAD_CHUNK_BYTES` | `52428800` | Trozo de tus en el navegador |
| `BACKUP_PATH` | `/srv/backups` | Copias locales |
| `BACKUP_RETENTION_DAYS` | `14` | Retención de copias |
| `BACKUP_RESTIC_REPOSITORY` | vacío | Copia remota propia (opcional) |
| `BACKUP_RESTIC_PASSWORD` | vacío | Clave de restic |
| `ADMIN_EMAILS` | `{{EMAIL_ADMIN}}` | Avisos y administradores |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | vacío | Acceso con Google (opcional) |
| `SMTP_URL`, `MAIL_FROM` | obligatorio | Correo saliente |
| `MAIL_SHARE_DAILY_LIMIT` | `10` | Envíos de resultados por correo al día por usuario |
| `GOOGLE_PICKER_CLIENT_ID`, `GOOGLE_PICKER_API_KEY`, `DROPBOX_APP_KEY` | vacío (desactivado) | Abrir y guardar en Google Drive y Dropbox |
| `GDRIVE_ENABLED`, `DROPBOX_ENABLED` | `false` | Flags de Google Drive y Dropbox |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | obligatorio | Antiabuso |
| `RATE_LIMIT_PER_MINUTE` | `60` | Por IP en la API |
| `ANON_TOKENS_PER_IP_DAY` | `10` | Tokens anónimos por IP y día (12.4) |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | modo test | Pagos |
| `STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_PRO_YEARLY` | modo test | Precios |
| `OPENROUTER_API_KEY` | obligatorio en producción | Clave de OpenRouter |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | API compatible con OpenAI |
| `LLM_PREFERRED_MODELS` | vacío | Lista ordenada de ids `:free` |
| `LLM_FALLBACK_ROUTER` | `openrouter/free` | Último recurso |
| `LLM_MODELS_REFRESH_HOURS` | `6` | Descubrimiento de modelos |
| `AI_DAILY_BUDGET` | `950` | Tope diario propio |
| `AI_PRO_RESERVE` | `400` | Reserva diaria para Pro |
| `AI_RPM_LIMIT` | `18` | Tope por minuto propio |
| `AI_BUDGET_RESET_TZ` | `UTC` | Zona del reinicio diario |
| `AI_REQUIRE_CONSENT` | `true` | Consentimiento obligatorio |
| `AI_CHAT_RPM_SHARE` | `0.5` | Parte del límite por minuto que puede usar el chat |
| `AI_TASK_MAX_REQUESTS` | `20` | Peticiones máximas por tarea |
| `EMBEDDINGS_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Embeddings locales |
| `WHISPER_MODEL` | `small` | Transcripción local |
| `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE` | `cpu`, `int8` | Transcripción local |
| `TTS_ENGINE` | `kokoro` | Voz local |
| `TTS_VOICE_ES`, `TTS_VOICE_EN` | voces de Kokoro | Voces por idioma |
| `REMBG_MODEL` | `isnet-general-use` | Quitar fondo (6.4) |
| `SOUNDFONT_PATH` | banco con licencia comercial | MIDI a audio |
| `TECTONIC_BUNDLE_PATH` | ruta en la imagen | LaTeX sin red |
| `VIDEO_H264_ENCODING_ENABLED` | `false` | Codificación H.264 tras la revisión legal (11) |
| `HEVC_DECODE_ENABLED` | `false` | HEIC y vídeo HEVC tras la revisión legal (7.2) |
| `INVOICING_ES_ENABLED` | `false` | Herramientas que generan facturas (7.23) |
| `IMAGE_MAX_PIXELS` | `100000000` | Límite de píxeles de una imagen (12.3) |
| `RENDER_MAX_PIXELS` | `50000000` | Píxeles máximos por página rasterizada (12.3) |
| `OPENSCAD_TIMEOUT_SECONDS` | `60` | Sandbox de OpenSCAD |
| `WORKER_RUNTIME` | `runc` | `runsc` para gVisor |
| `CONCURRENCY_<GRUPO>` | ver sección 5.4 | Concurrencia por grupo |
| `THREADS_<GRUPO>` | ver sección 5.4 | Hilos por trabajo |
| `GOTENBERG_URL` | `http://gotenberg:3000` | Gotenberg sin red, para archivos subidos |
| `GOTENBERG_WEB_URL` | `http://gotenbergweb:3000` | Gotenberg para URL |
| `EGRESS_AI_URL` | `http://egressai:4750` | Proxy de salida hacia OpenRouter |
| `EGRESS_WEB_URL` | `http://egressweb:4750` | Proxy de salida hacia la web pública |
| `SIGN_PKCS11_MODULE`, `SIGN_PKCS11_TOKEN_LABEL`, `SIGN_PKCS11_KEY_LABEL`, `SIGN_PKCS11_PIN` | SoftHSM2 en desarrollo | Sello de la plataforma (10) |
| `SIGN_CERT_PATH`, `TSA_URL` | vacío en desarrollo | Cadena del sello y TSA |
| `SEAL_ENABLED`, `SEAL_DAILY_LIMIT` | `true`, `500` | Interruptor y límite diario del sello |
| `EUTL_LOTL_URL`, `EUTL_REFRESH_HOURS` | lista oficial de la Comisión Europea, `24` | Lista de confianza para verificar firmas |
| `KOSIT_VALIDATOR_PATH`, `KOSIT_SCENARIOS_PATH` | rutas en la imagen | Validación de factura electrónica |
| `OCR_MAX_LANGUAGES` | `3` | Idiomas simultáneos en ocr-pdf |
| `SENTRY_DSN` | vacío | Errores (opcional) |
| `UMAMI_URL`, `UMAMI_WEBSITE_ID` | vacío | Analítica (opcional) |
| `LOG_LEVEL` | `INFO` | Nivel de log |
| `TOOL_<SLUG>_ENABLED` | según fase | Flag por herramienta |

`.env.example` con todas ellas y valores de desarrollo.

Los límites por plan (duración de audio, triángulos y demás) no son variables de entorno: viven en `plans` (9.3).
~~~~

### P-55 · H-28, H-46, H-56 · §15: estructura con registro exportado, planes, políticas y especificación troceada

Sustituye las líneas 1070–1090 del original, desde «```text» hasta «```».

~~~~markdown
```text
.
├── apps/
│   ├── web/                    # Next.js: páginas, herramientas cliente, auth, admin
│   └── api/                    # FastAPI: app pública, app interna, ops
├── packages/
│   ├── core/                   # Python: registro, almacenamiento, límites, IA
│   ├── registry/               # registry.json y JSON Schema generados (5.2)
│   ├── tools/                  # Python: <grupo>/<slug>/spec.py e impl.py
│   └── client-tools/           # TypeScript: herramientas de navegador en Web Workers
├── workers/                    # Dockerfiles por grupo y arranque de Celery
├── config/
│   └── plans.yaml              # límites por plan (9.3)
├── infra/
│   ├── caddy/Caddyfile
│   ├── smokescreen/
│   │   ├── acl-ai.yaml
│   │   └── acl-web.yaml
│   ├── gotenberg/              # flags de gotenberg y gotenbergweb (12.2)
│   └── tusd/
├── scripts/                    # check_licenses.py, license_policy.yaml, check_images.sh, export_registry.py, fixtures/
├── tests/                      # pytest, fixtures, e2e con Playwright, k6
├── docs/
│   └── spec/                   # este documento troceado (sección 1)
├── docker-compose.yml          # desarrollo, con Mailpit y los dobles de 0.1
├── docker-compose.coolify.yml  # producción
└── .env.example
```
~~~~

### P-56 · H-01, H-02, H-05, H-12, H-13, H-14, H-16, H-34, H-41 · §16: pruebas automatizables de los riesgos nuevos

Sustituye las líneas 1096–1174 del original, desde «### 16.1 Generales» hasta «- verificar-firmas-pdf: detecta un cambio no permitido tras una firma de certificación.».

~~~~markdown
### 16.1 Generales

- **Python:** pytest con fixtures reales. Por herramienta comprueba:
  - tipo de salida por bytes;
  - número de páginas;
  - texto esperado;
  - cifrado;
  - PDF/A validado con veraPDF;
  - firma válida con pyHanko.
- **Web:**
  - Vitest para la lógica de las herramientas cliente;
  - Playwright para unir, comprimir, word-a-pdf, pdf-a-word, ogg-a-mp3, stl-a-3mf, chat-pdf con LLM falso y el flujo de pago con `FakePaymentProvider`; el pago con claves de prueba reales de Stripe se comprueba en el cierre operativo de F1;
  - Playwright también verifica que las herramientas cliente no envían el archivo a la red;
  - regresión visual: capturas de la plantilla de herramienta en móvil y escritorio, y de los PDF de folleto-pdf, varias-paginas-por-hoja, numerar-paginas-pdf y marca-de-agua-pdf pasados a PNG con pypdfium2, con un umbral de diferencia de píxeles;
  - Lighthouse CI según 1.3.
- **Registro:** `registry.json` está al día y el registro se importa en la API sin cargar motores (5.2).
- **Licencias e imágenes:** `check_licenses.py` y `check_images.sh` en la CI (11).
- **Carga:** k6 con 50 trabajos simultáneos de comprimir-pdf y 10 de ogg-a-mp3, más un pico de 300 trabajos ligeros en 5 minutos desde 100 clientes, midiendo CPU, RAM, disco y tiempo de respuesta de las páginas. Aparece `QUEUE_FULL` antes de que la espera supere el umbral y las páginas siguen por debajo de 1 s. Los resultados alimentan `docs/OPERATIONS.md` y los valores de 5.4.

### 16.2 Almacenamiento

- `pre-create` rechaza archivos por encima del plan, subidas con tamaño diferido (`Upload-Defer-Length`) y cualquier subida cuando la guarda de disco está activa.
- Un archivo cuyo tipo real no coincide con la extensión queda `rejected`, `POST /v1/jobs` responde `UNSUPPORTED_FORMAT` y la limpieza lo borra.
- `POST /v1/jobs` enviado justo después de terminar la subida funciona siempre, porque `pre-finish` es bloqueante.
- La reserva de disco impide aceptar más subidas de las que caben.
- Token de descarga caducado o manipulado: 403. Ruta con `..` en el nombre: rechazada. Caddy no lista directorios y envía las cabeceras de 4.4.
- Celery beat borra trabajos vencidos y huérfanos.
- `backup` y `restore` funcionan sobre una base de prueba, y `backup` sube la copia con restic a un servidor SFTP en contenedor.

### 16.3 IA

- La petición 951 del día se bloquea con `AI_BUDGET_EXHAUSTED`.
- Un usuario gratuito no consume la reserva Pro.
- El limitador respeta 18 peticiones por minuto y el reparto del chat.
- Si el primer modelo devuelve 429, la petición se resuelve con el siguiente candidato.
- Todas las peticiones llevan `provider.data_collection: "deny"`.
- El descubrimiento guarda los modelos de precio 0 con su `max_completion_tokens`.
- La reconciliación con `/key` sube el contador propio cuando OpenRouter cuenta más.
- Sin modelos válidos, la herramienta responde `AI_UNAVAILABLE` sin gastar peticiones.
- Sin consentimiento, 400.
- Las herramientas excluidas nunca llaman a OpenRouter (se prueba con un transporte que falla si se usa).
- La caché evita una segunda petición para la misma tarea del mismo usuario y nunca sirve el resultado de otro usuario.

### 16.4 Seguridad

- web-a-pdf y captura-web contra 169.254.169.254, localhost, el nombre de otro servicio y una IP privada alcanzada tras una redirección: bloqueadas.
- Desde cada worker y desde `gotenberg`, una conexión a internet falla; desde `workerai`, solo responde OpenRouter.
- Bombas de descompresión (ZIP, PNG gigante, PDF con una página enorme y XLSX con relación de compresión alta): cortadas.
- Tiempo límite: mata el proceso.
- Ningún secreto en logs ni en los argumentos de tareas guardados en Valkey.
- Matriz de secretos: cada contenedor arranca solo con sus variables (12.1).
- Lectura de archivos locales: un Markdown con `![](/proc/self/environ)` para pandoc, un `.tex` con `\input{/etc/hostname}`, un SVG con `<image href="file:///etc/hostname">`, un `.scad` con `import("/etc/hostname")` y un EPUB con `<img src="file:///etc/hostname">` se rechazan, o el resultado no contiene ese archivo ni ningún secreto.
- Una lista HLS que apunta a `/etc/passwd` o a una URL: rechazada.
- Un XML con entidad externa y un ZIP con rutas `../`: rechazados.
- Cabeceras CSP, HSTS y `Permissions-Policy` presentes en la web, y `Content-Security-Policy: default-src 'none'; sandbox` en `files`.
- `POST /v1/session/anon` por encima de `ANON_TOKENS_PER_IP_DAY` desde la misma IP: rechazado. Una cabecera `CF-Connecting-IP` falsificada desde fuera de los rangos de Cloudflare: ignorada.
- Webhook de Stripe con firma inválida: 400; el mismo evento dos veces: se procesa una vez.
- Redacción: tras redactar un área que cubre texto, parte de una imagen y un trazado vectorial, no queda el texto, los píxeles de la imagen bajo el área están sustituidos y el trazado ya no se dibuja en esa zona.

### 16.5 Formatos

- **Audio y vídeo:** duración conservada (±50 ms) y códec correcto, comprobados con ffprobe.
- **Firmas:** el documento extraído de un .csig o .p7m de prueba coincide byte a byte con el original; verificar-firma detecta un documento alterado.
- **Datos:**
  - GPX ↔ KML conserva el número de puntos;
  - VCF → CSV → VCF conserva los contactos;
  - arreglar-codificacion-csv recupera tildes y eñes.
- **3D:**
  - STL → 3MF → STL conserva volumen (error menor del 0,1 %) y número de triángulos;
  - STEP → STL sale estanco;
  - lib3mf valida cada 3MF generado;
  - reparar-stl deja estanca una malla de prueba con huecos;
  - bgcode → gcode → bgcode reproduce el G-code de archivos reales de PrusaSlicer;
  - OpenSCAD con `import` fuera del directorio del trabajo falla.
- **Vídeo:** un MOV con H.264 y AAC pasa a MP4 sin recodificar (mismo códec y mismo número de fotogramas).

### 16.6 Opciones (Anexo A)

- **Prueba de contrato por herramienta:** el `options_schema` publicado en `/v1/tools` tiene las opciones del Anexo A con sus valores por defecto y rangos, y la API rechaza valores fuera de rango con `INVALID_OPTIONS`.
- **Prueba de efecto** al menos para:
  - comprimir-pdf: con las opciones por defecto reduce un PDF con fotos; nunca devuelve un archivo mayor que el original; el texto extraído es idéntico al original.
  - numerar-paginas-pdf: patrón `{NUM} / {CNT}` con primera página 3 y primer número 1; el texto aparece donde toca.
  - marca-de-agua-pdf: el mosaico cubre la página.
  - proteger-pdf: cada permiso desactivado se refleja en el PDF; AES-256.
  - redactar-pdf: con cada método, el texto redactado ya no se encuentra en el resultado y se cumplen las comprobaciones de redacción de 16.4.
  - pdf-escala-de-grises: en las páginas no rasterizadas no queda ningún operador de color distinto de gris, el texto sigue siendo extraíble y el informe lista las páginas rasterizadas.
  - pdf-modo-oscuro: el texto sigue siendo extraíble y las imágenes no cambian en «conservar tonos».
  - ocr-pdf: con salida PDF/A pasa veraPDF.
  - unir-pdf: con «páginas en blanco tras archivos impares», cada documento empieza en página impar.
  - folleto-pdf: 10 páginas dan 12, con la contraportada al final.
  - imprimir-pdf: con 4 por hoja, el PDF de impresión tiene el número de hojas esperado.
  - pdf-a-tiff: en blanco y negro con G4, `tiffinfo` confirma la compresión.
  - generar-codigo-qr: con logotipo y corrección H, zxing-cpp lee el código.
  - crear-factura-electronica: el XML generado pasa el KoSIT Validator en cada perfil.
  - verificar-firmas-pdf: detecta un cambio no permitido tras una firma de certificación.
  - pdf-a-pdfa: un PDF con fuentes sin incrustar falla con un informe y ofrece la alternativa rasterizada; en ningún momento se ejecuta Ghostscript.
  - quitar-fondo: el modelo cargado es el de `REMBG_MODEL`, nunca `bria-rmbg`.

### 16.7 Operación

- Restauración completa desde la copia remota en un entorno limpio de la CI (base de datos, variables cifradas y token del sello), una vez por fase.
- Arranque de humo del Compose de producción con sus healthchecks.
- Un worker que muere por memoria deja el trabajo en `WORKER_LOST` al tercer intento, sin bucles.
- Un trabajo más largo que una hora (el `visibility_timeout` por defecto) se ejecuta una sola vez.
~~~~

### P-57 · H-01, H-18, H-19, H-45 · §17: lista de lanzamiento y orden de ejecución de las fases

Sustituye las líneas 1180–1190 del original, desde «| Fase | Contenido | Se cierra cuando |» hasta «Las herramientas de la sección 7.23 entran en la fase que indica cada línea, y las opciones del Anexo A llegan con su herramienta. Ninguna fase se cierra con herramientas por debajo de esas opciones. Al cerrar F6, comprueba en `docs/TOOLS.md` que cada herramienta web de PDF24 tiene su equivalente o una explicación de por qué no.».

~~~~markdown
| Fase | Contenido | Cierre técnico (1.3) |
| --- | --- | --- |
| F1 Núcleo y lanzamiento | Monorepo, Compose local y de Coolify, autenticación, anónimos con cuotas, tusd, Caddy, trabajos, limpieza y guardas de disco y de colas, copias (también la remota), planes y Stripe, catálogo F1, conversor-pdf, convertir-a-pdf, panel de administración básico y las herramientas adelantadas de 17.1 | Pruebas de 16.1 a 16.4 y 16.7 de su ámbito en verde y Lighthouse según 1.3 |
| F2 PDF de servidor | Resto del catálogo F2, escáner, comparar y montar | Herramientas F2 en verde |
| F3 IA | Descubrimiento de modelos, limitador y presupuesto, consentimiento, embeddings y voz locales, catálogo F3 | Pruebas de 16.3 en verde y uso real de peticiones registrado |
| F4 Firma y extras | Firma, compartir, solicitar firmas, PDF/UA y facturas (validar y visualizar primero; los generadores detrás de `INVOICING_ES_ENABLED`) | Firma validada con pyHanko y flujo de solicitud probado de extremo a extremo |
| F5 Multimedia | Audio, vídeo (solo Pro), imágenes, IA de audio y vídeo, convertir-archivo | Pruebas de audio y vídeo y prueba de carga de ogg-a-mp3 |
| F6 Utilidades | Documentos y datos, comprimidos, subtítulos, fuentes, firmados y factura electrónica, GPS, contactos y calendario, diagramas, música, captura web | Pruebas de 16.5 de su ámbito en verde |
| F7 Impresión 3D y CAD | Mallas, CAD, herramientas, generadores, G-code, convertir-modelo-3d | Pruebas 3D de 16.5 en verde |

Las fases conservan su número porque las líneas del catálogo lo citan, pero se ejecutan en este orden: núcleo de F1 y lista de lanzamiento (17.1), lanzamiento público, resto de F1, F2, F5 sin vídeo, F3, F4, F6, vídeo de F5 y F7. Cada fase tiene además su cierre operativo (1.3).

### 17.1 Lista de lanzamiento

El lanzamiento público solo necesita el núcleo de F1 y estas herramientas. Las demás de F1 pueden quedar con `noindex` (7.22) hasta terminarse después del lanzamiento.

- **Navegador:** unir-pdf, dividir-pdf, girar-pdf, eliminar-paginas-pdf, extraer-paginas-pdf, organizar-pdf, numerar-paginas-pdf, marca-de-agua-pdf, editar-pdf, rellenar-pdf, jpg-a-pdf, png-a-pdf, imagenes-a-pdf, pdf-a-jpg, pdf-a-png, pdf-a-imagenes, generar-contrasena; y se adelantan de F5 png-a-jpg, webp-a-jpg, comprimir-imagen y redimensionar-imagen.
- **Servidor:** comprimir-pdf, convertir-a-pdf, word-a-pdf, excel-a-pdf, ppt-a-pdf; y se adelantan de F2 pdf-a-word, ocr-pdf, proteger-pdf y desbloquear-pdf, y de F5 ogg-a-mp3, opus-a-mp3, m4a-a-mp3 y mp4-a-mp3.
- Cada herramienta adelantada llega con todas sus opciones del Anexo A.

Las herramientas de la sección 7.23 entran en la fase que indica cada línea, y las opciones del Anexo A llegan con su herramienta. Ninguna fase se cierra con herramientas por debajo de esas opciones, salvo las desactivadas según 1.7. Al cerrar F6, comprueba en `docs/TOOLS.md` que cada herramienta web de PDF24 tiene su equivalente o una explicación de por qué no.
~~~~

### P-58 · H-01, H-02, H-05, H-08, H-16 · §18: criterios de aceptación verificables

Sustituye las líneas 1196–1207 del original, desde «- `docker compose up` arranca todo en local solo con `.env.example`.» hasta «- `docs/` completo: PLAN, PROGRESS, DECISIONS, ARCHITECTURE, TOOLS, LICENSES, LEGAL, SECURITY, DEPLOY y OPERATIONS.».

~~~~markdown
- `docker compose up` arranca todo en local solo con `.env.example` y los dobles de 0.1.
- El cierre técnico de cada fase está en verde en la CI, y el operativo está hecho o figura como pendiente en `docs/PROGRESS.md`, con sus pasos en `docs/DEPLOY-CHECKLIST.md`.
- Con las entradas de 0.1, el repositorio se despliega en un único VPS con Coolify v4 con todos los healthchecks en verde.
- No existe ninguna dependencia ni variable de S3: todo el almacenamiento está en disco del VPS.
- Cada herramienta habilitada tiene páginas es y en, funciona de extremo a extremo y su prueba pasa; las desactivadas cumplen 1.7.
- Cada herramienta expone como mínimo las opciones del Anexo A, con sus valores por defecto y rangos.
- Las herramientas cliente no envían el archivo a la red.
- La IA solo usa modelos gratuitos de OpenRouter con `data_collection: "deny"`, nunca supera 18 peticiones por minuto ni `AI_DAILY_BUDGET` al día, y exige consentimiento.
- Ninguna dependencia AGPL enlazada o empaquetada y ningún paquete GPL importado, comprobado en la CI.
- Ningún worker sale a internet salvo por los proxies de 12.2, y ningún contenedor ve secretos que no le tocan.
- Los archivos y el contenido derivado desaparecen al vencer su plazo.
- Las guardas de disco y de colas funcionan y avisan al administrador.
- La copia remota existe y la restauración está probada (16.7).
- Ningún secreto en el repositorio ni en los logs.
- `docs/` completo: PLAN, PROGRESS, DECISIONS, ARCHITECTURE, TOOLS, LICENSES, LEGAL, SECURITY, DEPLOY, DEPLOY-CHECKLIST, OPERATIONS, ERRORS y `spec/`.
~~~~

### P-59 · H-08, H-38 · A.1 web-a-pdf: documentos enlazados y campos reales de Gotenberg

Sustituye las líneas 1251–1261 del original, desde «- **web-a-pdf** (F1, Gotenberg con Chromium por el proxy de salida):» hasta «- Usa las opciones equivalentes de la ruta Chromium de Gotenberg que ofrezca la versión fijada.».

~~~~markdown
- **web-a-pdf** (F1, Chromium de `gotenbergweb` por `egressweb`):
  - URL de una página web o de un documento convertible (DOCX, XLSX, PPTX, ODT, imagen o PDF), que se descarga con los límites del plan y se convierte con su herramienta, como hace PDF24.
  - **Extra:**
    - Papel [A4] y Orientación [Vertical].
    - Márgenes [10 mm].
    - Imprimir fondos [sí].
    - Una sola página larga [no].
    - Tipo de medio [print] | screen.
    - Espera antes de capturar [1 s] (0–10).
    - Esquema de color [claro] | oscuro.
  - Usa los campos de la ruta Chromium de Gotenberg de la versión fijada: `paperWidth`, `paperHeight`, `landscape`, `marginTop` y el resto de márgenes, `printBackground`, `singlePage`, `emulatedMediaType`, `waitDelay` y `emulatedMediaFeatures` (`prefers-color-scheme`).
~~~~

### P-60 · H-20, H-42 · A.1 escribir-pdf: vista previa exacta e índice con números reales sin extensiones de pago

Sustituye las líneas 1271–1284 del original, desde «- **Vista previa por páginas** con el salto real de página.» hasta «- ODT con pandoc en servidor.».

~~~~markdown
  - **Vista previa por páginas:** el editor muestra saltos de página aproximados y el botón «Vista previa exacta» genera el PDF en servidor y lo muestra. No uses la extensión Pages de TipTap, que es de pago.
  - **El PDF exportado lleva:**
    - índice con los números de página reales, calculados en dos pasadas: se genera el PDF, se leen las páginas de cada título en el esquema que crea Gotenberg (`generateDocumentOutline`) y se vuelve a generar con los números;
    - campos rellenables insertados desde el editor (texto, casilla y fecha), creados con pdf-lib tras la conversión;
    - propiedades del documento (título, autor, asunto y palabras clave).
  - **Abrir:**
    - DOCX con mammoth;
    - ODT, convertido a HTML con LibreOffice en `workeroffice`;
    - Markdown;
    - PDF, convertido a HTML con Docling.
  - **Exportar:**
    - PDF: HTML enviado a Gotenberg, con marcadores desde los títulos (`generateDocumentOutline`) y PDF etiquetado (`generateTaggedPdf`).
    - DOCX con `docx`.
    - Markdown.
    - ODT con pandoc en servidor.
~~~~

### P-61 · H-52 · A.1 crear-collage: medidas de la foto del DNI con la norma vigente

Sustituye la línea 1306 del original: «- foto de carné 35 × 45 mm (UE y visados) y 26 × 32 mm (DNI y pasaporte españoles); comprueba las medidas oficiales vigentes antes de publicarlas;».

~~~~markdown
    - foto de carné 35 × 45 mm (UE y visados) y 32 mm de alto por 26 mm de ancho (DNI y pasaporte españoles; el RD 1553/2005 que fijaba esa medida para el DNI fue derogado por el RD 255/2025); comprueba las medidas oficiales vigentes antes de publicarlas;
~~~~

### P-62 · H-52 · A.1 generar-codigo-qr: PayPal con correo o identificador

Sustituye la línea 1342 del original: «- PayPal: enlace paypal.me con importe y moneda.».

~~~~markdown
    - PayPal: correo o identificador de PayPal.Me, importe y moneda.
~~~~

### P-63 · H-52 · A.1 generar-codigo-qr: rango del margen y valores por defecto del estilo

Sustituye las líneas 1347–1353 del original, desde «- margen [0] px.» hasta «- forma general [cuadrado] | círculo.».

~~~~markdown
    - margen [0] px (0–100).
    - Con logotipo se fuerza la corrección H.
  - **Estilo:**
    - fondo [#FFFFFF], módulos [#000000], ojos exteriores [#000000] y ojos interiores [#000000], cada uno con degradado opcional (lineal o radial, con ángulo de 0° a 315° en pasos de 45°);
    - forma de módulos y de ojos;
    - borde con grosor [5], espaciado [20] y color [#000000];
    - forma general [cuadrado] | círculo.
~~~~

### P-64 · H-10, H-11 · A.2 crear-factura-electronica: UBL, perfiles que no son EN 16931 y firma en el navegador

Sustituye las líneas 1378–1386 del original, desde «- **crear-factura-electronica** (F4, servidor):» hasta «- Antes de entregar, valida con el mismo motor que validar-factura-electronica.».

~~~~markdown
- **crear-factura-electronica** (F4, servidor; firma en el navegador; detrás de `INVOICING_ES_ENABLED`):
  - Formulario EN 16931 con validación en vivo de los campos obligatorios.
  - Formato de salida:
    - [Factur-X/ZUGFeRD], con perfil MINIMUM | BASIC WL | BASIC | [EN 16931] | EXTENDED | XRECHNUNG; MINIMUM y BASIC WL no son facturas EN 16931 completas y la interfaz lo avisa;
    - XRechnung CII | UBL;
    - Peppol BIS Billing 3.0;
    - UBL 2.1 (EN 16931), la sintaxis de la solución pública española;
    - Facturae 3.2.2, con firma XAdES-EPES opcional hecha en el navegador con xadesjs y el certificado del usuario o de su empresa (.p12 o .pfx abierto con PKI.js); la clave nunca sale del navegador.
  - Importar desde PDF: usa el flujo de pdf-a-factura-electronica.
  - Antes de entregar, valida con el mismo motor que validar-factura-electronica.
~~~~

### P-65 · H-43 · A.2 validar-factura-electronica: escenarios de 7.23

Sustituye la línea 1400 del original: «- Reglas: EN 16931, XRechnung, Peppol BIS, Factur-X/ZUGFeRD y Facturae (XSD y firma).».

~~~~markdown
  - Reglas: EN 16931, XRechnung, Peppol BIS, Factur-X/ZUGFeRD y Facturae (XSD y firma), con los escenarios de KoSIT descritos en 7.23.
~~~~

### P-66 · H-55 · A.4 imprimir-pdf: alternativa cuando el navegador no imprime desde un iframe

Sustituye la línea 1553 del original: «- Implementación: genera un PDF de impresión con pdf-lib y lo imprime desde un iframe. Recuerda elegir «Tamaño real» en el diálogo.».

~~~~markdown
  - Implementación: genera un PDF de impresión con pdf-lib y lo imprime desde un iframe. Recuerda elegir «Tamaño real» en el diálogo. Si el navegador no imprime un PDF desde un iframe (Safari y la mayoría de móviles), ofrece descargar el PDF de impresión.
~~~~

### P-67 · H-40 · A.5 comprimir-pdf: reducción de fuentes segura

Sustituye la línea 1601 del original: «- Reducir fuentes incrustadas (subconjunto y duplicadas) [sí].».

~~~~markdown
    - Reducir fuentes incrustadas [sí]: quita fuentes duplicadas y no usadas; solo crea subconjuntos de fuentes TrueType o CFF simples cuyos glifos usados se puedan calcular con exactitud, y no toca las demás.
~~~~

### P-68 · H-40 · A.5 comprimir-pdf: cuatro opciones de borrado separadas, como en PDF24

Sustituye la línea 1607 del original: «- Quitar adjuntos, anotaciones, marcadores y metadatos [no].».

~~~~markdown
    - Quitar adjuntos [no].
    - Quitar anotaciones [no].
    - Quitar marcadores [no].
    - Quitar metadatos [no].
~~~~

### P-69 · H-41 · A.5 pdf-escala-de-grises: alternativa por página

Sustituye la línea 1611 del original: «- Método: [vectorial] (reescribe los operadores de color; el texto y los vectores siguen siendo vectores) | **Extra:** rasterizar todo.».

~~~~markdown
  - Método: [vectorial] (reescribe los operadores de color; el texto y los vectores siguen siendo vectores; las páginas que no se pueden convertir con seguridad se rasterizan en gris y se avisa) | **Extra:** rasterizar todo.
~~~~

### P-70 · H-24 · A.5 ocr-pdf: idiomas instalados, PDF/A sin Ghostscript y opciones de la v17

Sustituye las líneas 1626–1632 del original, desde «- Lista completa de Tesseract (unos 125), incluidos los CJK verticales y Fraktur.» hasta «- Texto existente: [omitir las páginas con texto] (`--skip-text`) | Forzar OCR (`--force-ocr`).».

~~~~markdown
    - Lista completa de Tesseract (unos 125) con `tessdata_fast`, incluidos los CJK verticales y Fraktur; `tessdata_best` para los nueve idiomas de la sección 2.
  - Salida: [PDF con capa de texto] | PDF/A-2b (`--output-type pdfa-2 --pdfa-backend internal`; si no se puede sin Ghostscript, error claro y opción de rasterizar) | **Extra:** TXT.
  - Enderezar [sí] (`--deskew`).
  - Autorrotar páginas [no] (`--rotate-pages`).
  - Quitar fondo [no]: con `--remove-background` si la versión fijada lo admite; si no, preprocesado propio con OpenCV.
  - Limpiar páginas [no] (`--clean`, con unpaper).
  - Texto existente: [omitir las páginas con texto] (`--skip-text`, o `--mode skip` en la v17) | Forzar OCR (`--force-ocr`, o `--mode force`).
~~~~

### P-71 · H-24 · A.5 pdf-a-pdfa: conversión sin Ghostscript y salida si no es posible

Sustituye las líneas 1645–1647 del original, desde «- **pdf-a-pdfa** (F2):» hasta «- Se valida con veraPDF y se adjunta el informe.».

~~~~markdown
- **pdf-a-pdfa** (F2):
  - Nivel: [PDF/A-2b] | 1b | 2u | 3b; 2a y 3a solo si el PDF está etiquetado.
  - Se valida con veraPDF y se adjunta el informe.
  - Conversión con OCRmyPDF (`--pdfa-backend internal`, sin OCR en las páginas que ya tienen texto). Si el archivo no se puede convertir sin Ghostscript (por ejemplo, por fuentes sin incrustar), la tarea falla con el informe y ofrece rasterizar las páginas con capa de texto OCR.
~~~~

### P-72 · H-09, H-10 · A.6 firmar-pdf: el certificado de la empresa también por firma interrumpida

Sustituye la línea 1676 del original: «- certificado [sello de la plataforma o de la empresa], en servidor por PKCS#11 | certificado propio .p12/.pfx con firma interrumpida (la clave no sale del navegador);».

~~~~markdown
    - certificado [sello de la plataforma], en servidor por PKCS#11 | certificado propio o de la empresa (.p12 o .pfx) con firma interrumpida: el servidor prepara el PDF y el resumen, el navegador firma con WebCrypto tras abrir el archivo con PKI.js, y la clave no sale del navegador;
~~~~

### P-73 · H-12 · A.6 redactar-pdf: rasterizar por defecto y verificación completa

Sustituye las líneas 1685–1689 del original, desde «- Método:» hasta «- Tras guardar, se busca el texto redactado en el resultado; si aparece, la tarea falla.».

~~~~markdown
  - Método:
    - [Rasterizar las páginas afectadas] a 300 ppp, como hace PDF24: elimina con seguridad texto, imágenes y vectores bajo el área; el resto de la página pierde la selección de texto y se ofrece pasar ocr-pdf;
    - Eliminar solo el contenido bajo el área, con EmbedPDF y PDFium, que conserva el texto del resto de la página. Solo se ofrece cuando pasa las pruebas de redacción de 16.4 con texto, imágenes y vectores.
  - Siempre quita también los metadatos.
  - Tras guardar, se comprueba el resultado: el texto redactado no aparece, no queda texto dentro de las áreas y los píxeles de las imágenes bajo las áreas están sustituidos. Si algo falla, la tarea falla.
~~~~

### P-74 · H-39 · A.7 comparar-pdf: dónde se procesa

Sustituye la línea 1707 del original: «- **comparar-pdf** (F2):».

~~~~markdown
- **comparar-pdf** (F2, en el navegador; en servidor solo con archivos de más de `CLIENT_MAX_MB`):
~~~~

### P-75 · H-20 · A.9: modo fiel al diseño en workeroffice

Sustituye la línea 1806 del original: «- Fiel al diseño: cajas posicionadas, con la importación de PDF de LibreOffice. Se avisa de que se edita peor.».

~~~~markdown
    - Fiel al diseño: cajas posicionadas, con la importación de PDF de LibreOffice en `workeroffice`. Se avisa de que se edita peor.
~~~~

### P-76 · H-39 · A.10: SVG en el navegador

Sustituye la línea 1831 del original: «- **svg-a-png y svg-a-jpg** (resvg):».

~~~~markdown
- **svg-a-png y svg-a-jpg** (navegador, `@resvg/resvg-wasm`):
~~~~

### P-77 · H-08 · A.7 verificar-firmas-pdf: revocación por egressweb

Sustituye la línea 1737 del original: «- **Revocación OCSP/CRL:** [bajo petición], por el proxy de salida.».

~~~~markdown
  - **Revocación OCSP/CRL:** [bajo petición], por `egressweb`.
~~~~

### P-78 · H-22 · A.8 HEIC: flag común de HEVC

Sustituye la línea 1782 del original: «- **HEIC:** solo con `HEIC_ENABLED`. Si está apagado, la página explica cómo exportar a JPEG desde iPhone y Mac.».

~~~~markdown
- **HEIC:** solo con `HEVC_DECODE_ENABLED`. Si está apagado, la página explica cómo exportar a JPEG desde iPhone y Mac.
~~~~

### P-79 · H-22 · A.10 heic: flag común de HEVC

Sustituye la línea 1838 del original: «- Solo con `HEIC_ENABLED`.».

~~~~markdown
  - Solo con `HEVC_DECODE_ENABLED`.
~~~~

---

Lo que no debe tocarse: el almacenamiento en disco con tus y `forward_auth`, el registro único de herramientas, el limitador atómico de IA en Valkey, la política de no enlazar AGPL y las pruebas de efecto por opción del Anexo A.
