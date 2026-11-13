### A.10 Imágenes

- **svg-a-png y svg-a-jpg** (navegador, `@resvg/resvg-wasm`):
  - Tamaño: [original] | 2× | 3× | 4× | ancho personalizado [1000] px (1–16384), manteniendo la proporción.
  - JPG: fondo [blanco] y calidad [90] %.
- **webp-a-jpg y webp-a-png:**
  - JPG: calidad [90] % y fondo para la transparencia [blanco].
  - Conservar metadatos [no].
- **heic-a-jpg y heic-a-png:**
  - Solo con `HEVC_DECODE_ENABLED`.
  - JPG: calidad [90] %.
  - Conservar EXIF [sí], quitando el GPS [sí].
