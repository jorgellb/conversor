## 17. Fases y entregables

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

---
