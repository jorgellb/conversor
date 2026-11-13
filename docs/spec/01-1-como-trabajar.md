## 1. Cómo trabajar

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

---
