## 6. IA con modelos gratuitos de OpenRouter

### 6.1 Condiciones de OpenRouter que condicionan el diseño

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

### 6.2 Descubrimiento de modelos

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

### 6.3 Presupuesto y limitador

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

### 6.4 Componentes locales (no gastan peticiones)

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

### 6.5 Diseño para gastar pocas peticiones

- Una sola llamada por tarea siempre que el documento quepa en el contexto del modelo elegido; si no, por bloques grandes, no por página.
- Chat: el documento entero en contexto si cabe; si no, recuperación local con pgvector y 6 a 8 fragmentos.
- Salida JSON:
  - con `response_format` y esquema si el modelo lo admite;
  - si no, instrucciones estrictas, parseo tolerante y como máximo 1 petición de reparación.
- Caché por `(propietario, sha256, herramienta, opciones, idioma)` con la misma caducidad que los archivos del usuario. Repetir una tarea no gasta. No se comparte entre usuarios: hacerlo revelaría si otra persona ha procesado el mismo documento.
- Límite de páginas por tarea de IA según el plan (sección 9.3).

### 6.6 Privacidad y consentimiento

- Antes de la primera tarea de IA de cada sesión, la interfaz muestra este aviso con casilla obligatoria:
  > «Para esta herramienta, el texto de tu documento se envía a un proveedor de IA externo a través de OpenRouter, que puede estar fuera de la Unión Europea. Solo usamos proveedores que declaran no entrenar con los datos, pero pueden conservarlos un tiempo según su política. No la uses con documentos confidenciales ni con datos personales de terceros.»
- Sin consentimiento, la API devuelve 400 (`AI_CONSENT_REQUIRED`). `AI_REQUIRE_CONSENT` está a `true` y no puede desactivarse en producción. Cada consentimiento se guarda en `ai_consents` con la fecha y la versión del texto.
- Nunca se envía a OpenRouter contenido de las herramientas de firma, verificación de firmas, contactos, calendario, correo o certificados. Esas herramientas no tienen opción de IA.
- `provider.data_collection: "deny"` va en todas las peticiones y no se puede cambiar en producción.
- La política de privacidad lista a OpenRouter y a sus proveedores como destinatarios, explica la posible transferencia fuera de la UE y enlaza a sus políticas. Añade en `docs/LEGAL.md` que debe revisarlo un especialista en protección de datos, junto con una evaluación de impacto (EIPD) del tratamiento con IA.
- Interfaz `LLMProvider` para cambiar en el futuro a modelos de pago con retención cero sin tocar las herramientas.
- Proveedor falso determinista cuando `OPENROUTER_API_KEY` está vacío y `APP_ENV=development`.

---
