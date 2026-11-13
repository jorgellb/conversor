## 8. Frontend y SEO

### 8.1 Páginas

- `/es` y `/en`:
  - portada con buscador de herramientas;
  - favoritos (estrella en cada herramienta), usadas recientemente y usadas con frecuencia, guardados en el navegador y, con sesión iniciada, en la cuenta;
  - categorías (PDF, Office, Imagen, Audio, Vídeo, IA, Datos, 3D, Firma, Facturas);
  - herramientas más usadas.
- `/es/<slug>`: una página por herramienta, generada en compilación desde el registro.
- `/es/convertir-archivo` y `/es/convertir-modelo-3d`.
- `/es/precios`, `/es/privacidad`, `/es/terminos`, `/es/aviso-legal`, `/es/ayuda`, `/es/contacto`.
- `/cuenta`: historial de trabajos (solo metadatos), plan, uso diario (tareas, peticiones de IA), facturación con el portal de cliente de Stripe y borrado de cuenta.
- `/admin` (rol administrador):
  - colas por grupo;
  - uso de disco;
  - presupuesto de IA del día y saldo de OpenRouter;
  - lista de modelos;
  - tasa de error por herramienta;
  - flags de herramientas;
  - purga manual de archivos.

### 8.2 Plantilla de página de herramienta

1. H1 con la acción («Convertir OGG a MP3») y subtítulo de una línea.
2. Zona de subida (arrastrar, varios archivos, pegar desde el portapapeles) con el aviso de dónde se procesa:
   - herramientas cliente: «Tu archivo no sale de tu dispositivo»;
   - herramientas servidor: «Se borra en 1 hora».
3. Opciones de la herramienta, generadas desde `options_schema` y nunca menos que las del Anexo A:
   - las básicas, visibles;
   - el resto, en un bloque plegado «Opciones adicionales»;
   - las últimas opciones usadas se recuerdan por herramienta en el navegador;
   - las opciones que dependen de otra (por ejemplo, las de cada formato de salida) solo aparecen cuando aplican.
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

### 8.3 Rendimiento y accesibilidad

- WebAssembly y librerías pesadas cargadas solo al elegir archivo; procesamiento en Web Workers.
- Objetivo: Lighthouse móvil de 90 o más en rendimiento y accesibilidad en las páginas de aterrizaje.
- PWA instalable; las herramientas cliente funcionan sin conexión.
- Modo oscuro, navegación por teclado y etiquetas accesibles.
- Textos de interfaz y SEO en archivos de mensajes por idioma, en español de España.

---
