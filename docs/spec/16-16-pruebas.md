## 16. Pruebas

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

---
