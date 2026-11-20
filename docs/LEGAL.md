# Revisiones legales (0.1 y 11)

Las anota el propietario con fecha y responsable. Mientras falten, los flags correspondientes siguen apagados.

| Asunto | Estado | Efecto mientras falte |
| --- | --- | --- |
| Textos de privacidad, términos y aviso legal (datos del titular entre corchetes en `apps/web/src/components/legal.ts`) | Pendiente | No publicar el sitio |
| HEVC (HEIC y vídeo H.265): licencias de patentes también para servicios en la nube | Pendiente | `HEVC_DECODE_ENABLED=false` |
| Codificación H.264 | Pendiente | `VIDEO_H264_ENCODING_ENABLED=false` |
| AAC, VP9 y AV1: pools que reclaman licencias | Pendiente | pptx-a-video codifica VP9 (WebM) y AV1 (MP4) con el FFmpeg LGPL (F6-C, D-237): sus autores (Google y AOMedia) los publican libres de regalías, pero hay pools (Sisvel) que reclaman licencias; revisar antes de abrir el plan Pro al público |
| MP3, Opus, Vorbis y FLAC | Riesgo bajo (patentes de MP3 caducadas) | ogg-a-mp3, opus-a-mp3, m4a-a-mp3 y mp4-a-mp3 activas |
| Factura electrónica (generadores): crear-factura (F4-E1) avisa de que no es un sistema de facturación verificable (Veri*factu, RD 1007/2023 y RDL 15/2025) y solo genera el PDF; el asesor confirma ese texto y si basta para publicarla, y revisa los generadores de factura electrónica (RD 238/2026) antes de encenderlos | Pendiente | `INVOICING_ES_ENABLED=false` y `TOOL_<SLUG>_ENABLED` sin definir |
| IA (OpenRouter, consentimiento, transferencias): un especialista en protección de datos revisa el aviso de 6.6, la política de privacidad (OpenRouter y sus proveedores como destinatarios, transferencia fuera de la UE) y la EIPD de abajo | Pendiente | Herramientas de IA en beta con el aviso y el consentimiento; no anunciarlas hasta la revisión |
| Pagos: alta en OSS si se vende a consumidores de otros países de la UE, Stripe Tax, precios, desistimiento y reembolsos | Pendiente | Stripe en modo test |
| Modelos de Docling | Revisar la ficha de licencia de cada modelo descargado en la imagen `worker-convert` | No publicar `pdf-a-word` editable sin la revisión |

## Evaluación de impacto (EIPD) del uso de IA con modelos de terceros (6.6 y 12.5)

Borrador para revisar con un especialista en protección de datos antes de anunciar las herramientas de IA.

| Punto | Situación |
| --- | --- |
| Tratamiento | Texto de los documentos que el usuario decide enviar a una herramienta de IA (resumir, y las que lleguen en F3), enviado a modelos gratuitos a través de OpenRouter |
| Base jurídica | Consentimiento (art. 6.1.a RGPD): aviso de 6.6 con casilla obligatoria antes de la primera tarea de cada sesión; se guarda la fecha y la versión del texto (`ai_consents`) |
| Quién puede usarlo | Solo usuarios con cuenta (los anónimos tienen 0 peticiones, 9.3) |
| Destinatarios | OpenRouter (EE. UU.) y el proveedor del modelo al que se dirige cada petición, que puede estar fuera de la UE; garantía de transferencia por confirmar en sus condiciones |
| Minimización | Solo el texto de las páginas elegidas; nunca contenido de firma, certificados, contactos, calendario o correo (comprobado en el código y en las pruebas); nada de metadatos del usuario en las peticiones |
| Política de datos | Todas las peticiones llevan `provider.data_collection: "deny"` (proveedores que declaran no recoger los datos para entrenar), fijo en el código; la cuenta de OpenRouter, sin entrenar ni publicar (`OPERATIONS.md`). Pueden conservar los datos un tiempo según su política |
| Conservación propia | Texto extraído y resultados: lo que duren los archivos (1 h o 24 h); registro de peticiones sin contenido: 90 días |
| Riesgos | Documento con datos de terceros enviado sin base adecuada (mitigación: aviso que lo desaconseja); retención del proveedor; cambio de las condiciones de OpenRouter o de un proveedor (mitigación: `data_collection` en cada petición y modelos que se apartan solos si no la cumplen) |
| Pendiente | Revisión por el especialista; decidir si hace falta un contrato de encargado con OpenRouter; revisar la transferencia internacional |

## Firma y verificación de firmas (10 y 7.23, F4)

- verificar-firmas-pdf muestra un nivel técnico (simple, avanzada, avanzada con certificado cualificado o cualificada) a
  partir de lo que contiene el archivo y de la lista de confianza de la UE. No es un dictamen: el valor jurídico según el
  Reglamento eIDAS depende de circunstancias que el PDF no recoge, y la página y el informe lo dicen. Los niveles que se
  prometan en la interfaz o en el marketing deben revisarse con un especialista antes de anunciarlos (10).
- La lista de confianza se descarga de la Comisión Europea y de los Estados miembros; el informe indica la fecha de la
  copia usada y avisa si está desactualizada.
- El sello de la plataforma (F4-A2) no es cualificado con un token software y no se anuncia como tal (10).
- solicitar-firmas (F4-C2, D-202) se presenta como firma electrónica simple con el sello de la plataforma y un registro
  de auditoría (verificación por un código enviado al correo), nunca como avanzada ni cualificada; la página, el correo y
  el certificado lo dicen. Por revisar con el asesor antes del lanzamiento: el texto del consentimiento que acepta el
  firmante, el plazo de conservación de `audit_events` (hoy se borran, con los trabajos internos que los copian, al borrar la
  solicitud o la cuenta del propietario;
  12.5 deja el plazo al asesor) y los 30 días que se guardan el documento firmado y el certificado.
