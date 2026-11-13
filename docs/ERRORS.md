# Códigos de error (5.3)

Códigos estables que devuelven la API (`error.code`) y las herramientas de navegador. Generado por `scripts/gen_docs.py` desde `packages/core/core/errors.py`.

| Código | Mensaje (es) | Mensaje (en) |
| --- | --- | --- |
| `FILE_TOO_LARGE` | El archivo supera el tamaño máximo de tu plan. | The file exceeds your plan's size limit. |
| `TOO_MANY_FILES` | Has añadido más archivos de los que admite tu plan en una tarea. | You added more files than your plan allows per task. |
| `UNSUPPORTED_FORMAT` | El formato real del archivo no es compatible con esta herramienta. | The file's real format is not supported by this tool. |
| `PASSWORD_REQUIRED` | El PDF está protegido: escribe su contraseña. | The PDF is protected: enter its password. |
| `WRONG_PASSWORD` | La contraseña no es correcta. | The password is not correct. |
| `INVALID_OPTIONS` | Alguna opción no es válida. | Some option is not valid. |
| `QUOTA_EXCEEDED` | Has llegado al límite diario de tu plan. Vuelve mañana o pásate a Pro. | You reached your plan's daily limit. Come back tomorrow or upgrade to Pro. |
| `QUEUE_FULL` | Ahora mismo hay mucha cola. Inténtalo en unos minutos o usa la versión del navegador si existe. | The queue is very long right now. Try again in a few minutes or use the browser version if available. |
| `DISK_FULL` | Servicio saturado, inténtalo en unos minutos. | Service busy, please try again in a few minutes. |
| `TIMEOUT` | El proceso ha tardado demasiado y se ha detenido. | Processing took too long and was stopped. |
| `WORKER_LOST` | El proceso se interrumpió varias veces y se ha cancelado. | Processing was interrupted several times and was cancelled. |
| `NOT_FOUND` | No se ha encontrado. | Not found. |
| `UNAUTHORIZED` | Hace falta identificarse. | Authentication required. |
| `FORBIDDEN` | No tienes permiso para esta acción. | You are not allowed to do this. |
| `TOOL_DISABLED` | Esta herramienta no está disponible ahora mismo. | This tool is not available right now. |
| `TURNSTILE_FAILED` | No hemos podido comprobar que no eres un robot. | We could not verify that you are human. |
| `RATE_LIMITED` | Demasiadas peticiones. Espera un momento. | Too many requests. Please wait a moment. |
| `CORRUPT_FILE` | El archivo está dañado o no se puede leer. | The file is damaged or cannot be read. |
| `LIMIT_EXCEEDED` | El archivo supera un límite de tu plan (páginas, duración o tamaño). | The file exceeds a limit of your plan (pages, duration or size). |
| `ENGINE_FAILED` | No se ha podido procesar el archivo. | The file could not be processed. |
| `PDFA_NEEDS_GHOSTSCRIPT` | Este PDF no se puede convertir a PDF/A sin rasterizarlo. Puedes repetir con la opción de rasterizar. | This PDF cannot be converted to PDF/A without rasterizing it. You can retry with the rasterize option. |
| `NOT_SMALLER` | No se ha podido reducir más: te devolvemos el original. | It could not be made smaller: you get the original back. |
| `AI_CONSENT_REQUIRED` | Hace falta tu consentimiento para usar la IA. | Your consent is required to use AI. |
| `AI_BUDGET_EXHAUSTED` | Se ha agotado la IA de hoy. | Today's AI budget is exhausted. |
| `AI_UNAVAILABLE` | La IA no está disponible temporalmente. | AI is temporarily unavailable. |
| `REDACTION_FAILED` | La comprobación de la redacción ha fallado: el resultado no se entrega. | The redaction check failed: the result is not delivered. |
| `URL_UNREACHABLE` | No se ha podido abrir esa dirección: comprueba que existe y que es pública. | That address could not be opened: check that it exists and is public. |
| `MAIL_FAILED` | No se ha podido enviar el correo. Inténtalo de nuevo más tarde. | The email could not be sent. Please try again later. |
| `NO_IMAGES` | El PDF no contiene imágenes que extraer con esas opciones. | The PDF contains no images to extract with those options. |
| `NO_TABLES` | No se han encontrado tablas en el PDF. Prueba con PDF a Excel, que también saca el texto, o pasa antes ocr-pdf si es un escaneo. | No tables were found in the PDF. Try PDF to Excel, which also extracts the text, or run OCR PDF first if it is a scan. |
| `NO_SPEECH` | No se ha encontrado voz en el audio: comprueba que el archivo tiene sonido y que no es solo música o silencio. | No speech was found in the audio: check that the file has sound and is not just music or silence. |
| `PRINT_RESTRICTED` | Este PDF no permite imprimir. Si tienes la contraseña de propietario, quita la restricción con «Desbloquear PDF». | This PDF does not allow printing. If you have the owner password, remove the restriction with “Unlock PDF”. |
| `INTERNAL` | Ha ocurrido un error inesperado. | An unexpected error occurred. |
