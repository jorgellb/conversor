# Origen de las muestras de prueba

Todas las muestras se generan al ejecutar las pruebas, salvo una de terceros, de dominio público:

- `jfk.ogg`: 11 s del discurso inaugural de J. F. Kennedy (20 de enero de 1961), obra del Gobierno federal de EE. UU.
  (dominio público). Es la muestra de las pruebas de faster-whisper (`tests/data/jfk.flac` de
  https://github.com/SYSTRAN/faster-whisper), pasada a Opus mono de 24 kbps. Una voz no se puede generar sin un
  sintetizador (D-114).

- `scripts/fixtures/generate.py` (Pillow, pikepdf, img2pdf, FFmpeg y LibreOffice si está instalado): PDF con texto y con
  fotos, PDF escaneado, PDF cifrado, JPG, PNG, WEBP, TIFF multipágina, OGG, Opus, M4A, MP4, DOCX, un PDF falso y una
  lista HLS para las pruebas de seguridad.
- `packages/client-tools/test/images.fixture.ts`: imágenes mínimas (40 × 20 y 30 × 30 píxeles) generadas con Pillow.
- Las pruebas de TypeScript crean sus PDF con `@cantoo/pdf-lib`.
- Fuentes Noto (OFL-1.1) de https://github.com/notofonts, en `apps/web/public/fonts/` con su licencia.
