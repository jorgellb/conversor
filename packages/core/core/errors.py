"""Códigos de error estables con mensaje traducido (docs/ERRORS.md)."""
from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    TOO_MANY_FILES = "TOO_MANY_FILES"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    PASSWORD_REQUIRED = "PASSWORD_REQUIRED"
    WRONG_PASSWORD = "WRONG_PASSWORD"
    INVALID_OPTIONS = "INVALID_OPTIONS"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    QUEUE_FULL = "QUEUE_FULL"
    DISK_FULL = "DISK_FULL"
    TIMEOUT = "TIMEOUT"
    WORKER_LOST = "WORKER_LOST"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    TOOL_DISABLED = "TOOL_DISABLED"
    TURNSTILE_FAILED = "TURNSTILE_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    CORRUPT_FILE = "CORRUPT_FILE"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    ENGINE_FAILED = "ENGINE_FAILED"
    PDFA_NEEDS_GHOSTSCRIPT = "PDFA_NEEDS_GHOSTSCRIPT"
    NOT_SMALLER = "NOT_SMALLER"
    AI_CONSENT_REQUIRED = "AI_CONSENT_REQUIRED"
    AI_BUDGET_EXHAUSTED = "AI_BUDGET_EXHAUSTED"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    REDACTION_FAILED = "REDACTION_FAILED"
    URL_UNREACHABLE = "URL_UNREACHABLE"
    MAIL_FAILED = "MAIL_FAILED"
    NO_IMAGES = "NO_IMAGES"
    NO_TABLES = "NO_TABLES"
    NO_SPEECH = "NO_SPEECH"
    PRINT_RESTRICTED = "PRINT_RESTRICTED"
    INTERNAL = "INTERNAL"


MESSAGES: dict[str, dict[str, str]] = {
    "PRINT_RESTRICTED": {"es": "Este PDF no permite imprimir. Si tienes la contraseña de propietario, quita la restricción con «Desbloquear PDF».",
                         "en": "This PDF does not allow printing. If you have the owner password, remove the restriction with “Unlock PDF”."},
    "NO_SPEECH": {"es": "No se ha encontrado voz en el audio: comprueba que el archivo tiene sonido y que no es solo música o silencio.",
                  "en": "No speech was found in the audio: check that the file has sound and is not just music or silence."},
    "NO_IMAGES": {"es": "El PDF no contiene imágenes que extraer con esas opciones.", "en": "The PDF contains no images to extract with those options."},
    "NO_TABLES": {"es": "No se han encontrado tablas en el PDF. Prueba con PDF a Excel, que también saca el texto, o pasa antes ocr-pdf si es un escaneo.",
                  "en": "No tables were found in the PDF. Try PDF to Excel, which also extracts the text, or run OCR PDF first if it is a scan."},
    "MAIL_FAILED": {"es": "No se ha podido enviar el correo. Inténtalo de nuevo más tarde.",
                    "en": "The email could not be sent. Please try again later."},
    "URL_UNREACHABLE": {"es": "No se ha podido abrir esa dirección: comprueba que existe y que es pública.",
                        "en": "That address could not be opened: check that it exists and is public."},
    "REDACTION_FAILED": {"es": "La comprobación de la redacción ha fallado: el resultado no se entrega.", "en": "The redaction check failed: the result is not delivered."},
    "FILE_TOO_LARGE": {"es": "El archivo supera el tamaño máximo de tu plan.", "en": "The file exceeds your plan's size limit."},
    "TOO_MANY_FILES": {"es": "Has añadido más archivos de los que admite tu plan en una tarea.", "en": "You added more files than your plan allows per task."},
    "UNSUPPORTED_FORMAT": {"es": "El formato real del archivo no es compatible con esta herramienta.", "en": "The file's real format is not supported by this tool."},
    "PASSWORD_REQUIRED": {"es": "El PDF está protegido: escribe su contraseña.", "en": "The PDF is protected: enter its password."},
    "WRONG_PASSWORD": {"es": "La contraseña no es correcta.", "en": "The password is not correct."},
    "INVALID_OPTIONS": {"es": "Alguna opción no es válida.", "en": "Some option is not valid."},
    "QUOTA_EXCEEDED": {"es": "Has llegado al límite diario de tu plan. Vuelve mañana o pásate a Pro.", "en": "You reached your plan's daily limit. Come back tomorrow or upgrade to Pro."},
    "QUEUE_FULL": {"es": "Ahora mismo hay mucha cola. Inténtalo en unos minutos o usa la versión del navegador si existe.", "en": "The queue is very long right now. Try again in a few minutes or use the browser version if available."},
    "DISK_FULL": {"es": "Servicio saturado, inténtalo en unos minutos.", "en": "Service busy, please try again in a few minutes."},
    "TIMEOUT": {"es": "El proceso ha tardado demasiado y se ha detenido.", "en": "Processing took too long and was stopped."},
    "WORKER_LOST": {"es": "El proceso se interrumpió varias veces y se ha cancelado.", "en": "Processing was interrupted several times and was cancelled."},
    "NOT_FOUND": {"es": "No se ha encontrado.", "en": "Not found."},
    "UNAUTHORIZED": {"es": "Hace falta identificarse.", "en": "Authentication required."},
    "FORBIDDEN": {"es": "No tienes permiso para esta acción.", "en": "You are not allowed to do this."},
    "TOOL_DISABLED": {"es": "Esta herramienta no está disponible ahora mismo.", "en": "This tool is not available right now."},
    "TURNSTILE_FAILED": {"es": "No hemos podido comprobar que no eres un robot.", "en": "We could not verify that you are human."},
    "RATE_LIMITED": {"es": "Demasiadas peticiones. Espera un momento.", "en": "Too many requests. Please wait a moment."},
    "CORRUPT_FILE": {"es": "El archivo está dañado o no se puede leer.", "en": "The file is damaged or cannot be read."},
    "LIMIT_EXCEEDED": {"es": "El archivo supera un límite de tu plan (páginas, duración o tamaño).", "en": "The file exceeds a limit of your plan (pages, duration or size)."},
    "ENGINE_FAILED": {"es": "No se ha podido procesar el archivo.", "en": "The file could not be processed."},
    "PDFA_NEEDS_GHOSTSCRIPT": {"es": "Este PDF no se puede convertir a PDF/A sin rasterizarlo. Puedes repetir con la opción de rasterizar.", "en": "This PDF cannot be converted to PDF/A without rasterizing it. You can retry with the rasterize option."},
    "NOT_SMALLER": {"es": "No se ha podido reducir más: te devolvemos el original.", "en": "It could not be made smaller: you get the original back."},
    "AI_CONSENT_REQUIRED": {"es": "Hace falta tu consentimiento para usar la IA.", "en": "Your consent is required to use AI."},
    "AI_BUDGET_EXHAUSTED": {"es": "Se ha agotado la IA de hoy.", "en": "Today's AI budget is exhausted."},
    "AI_UNAVAILABLE": {"es": "La IA no está disponible temporalmente.", "en": "AI is temporarily unavailable."},
    "INTERNAL": {"es": "Ha ocurrido un error inesperado.", "en": "An unexpected error occurred."},
}


# Detalles con su propio texto (el código del error no cambia). El detalle llega como «clave:valores».
DETAILS: dict[str, dict[str, str]] = {
    # «ai_pages:150>30»: páginas del documento y máximo de páginas por tarea de IA del plan (9.3).
    "ai_pages": {"es": "Tu plan permite {max} páginas por tarea de IA y el documento tiene {need}: elige un rango de páginas.",
                 "en": "Your plan allows {max} pages per AI task and the document has {need}: choose a page range."},
    # «ai_task:25>20»: peticiones que necesita el documento y máximo por tarea (6.3).
    "ai_task": {"es": "Este documento necesitaría {need} peticiones de IA y tu plan permite {max} por tarea: elige un rango de páginas más corto.",
                "en": "This document would need {need} AI requests and your plan allows {max} per task: choose a shorter page range."},
    # «ai_files:25>20»: peticiones (una por archivo, ticket-a-excel) y máximo por tarea (6.3).
    "ai_files": {"es": "Estos archivos necesitarían {need} peticiones de IA (una por archivo) y tu plan permite {max} por tarea: sube menos a la vez.",
                 "en": "These files would need {need} AI requests (one per file) and your plan allows {max} per task: upload fewer at once."},
    # «ai_span:25>20»: peticiones que necesita una grabación o unos subtítulos y máximo por tarea (6.3, F3-E).
    "ai_span": {"es": "Esto necesitaría {need} peticiones de IA y tu plan permite {max} por tarea: elige un tramo más corto con «Desde» y «Hasta».",
                "en": "This would need {need} AI requests and your plan allows {max} per task: choose a shorter section with “From” and “To”."},
    # «audio_minutes:45>30»: minutos del tramo elegido y máximo de audio por tarea del plan (9.3).
    "audio_minutes": {"es": "Tu plan permite {max} minutos de audio por tarea y el tramo elegido dura {need}: elige un tramo más corto con «Desde» y «Hasta».",
                      "en": "Your plan allows {max} minutes of audio per task and the chosen section lasts {need}: choose a shorter one with “From” and “To”."},
    "subs_empty": {"es": "No hay texto que traducir en los subtítulos (o en el tramo elegido).",
                   "en": "There is no text to translate in the subtitles (or in the chosen section)."},
    "subs_range": {"es": "El tramo elegido no es válido: «Desde» tiene que ir antes de «Hasta» y dentro de la duración.",
                   "en": "The chosen section is not valid: “From” must come before “To” and within the duration."},
    "ai_day": {"es": "Has usado todas tus peticiones de IA de hoy.", "en": "You have used all your AI requests for today."},
    "chat_expired": {"es": "El documento de este chat ya no está: vuelve a prepararlo.",
                     "en": "This chat's document is no longer available: prepare it again."},
    "chat_not_ready": {"es": "El documento aún no está preparado.", "en": "The document is not ready yet."},
    "ai_same_language": {"es": "El idioma de origen y el de destino son el mismo.", "en": "The source and target languages are the same."},
    "ai_empty": {"es": "No se ha encontrado texto en las páginas elegidas.", "en": "No text was found in the selected pages."},
    "ai_account": {"es": "Las herramientas de IA necesitan una cuenta: inicia sesión o regístrate gratis.",
                   "en": "AI tools need an account: sign in or sign up for free."},
    "image_no_tables": {"es": "No se ha encontrado ninguna tabla en la imagen.", "en": "No table was found in the image."},
    "not_receipt": {"es": "La imagen no parece un ticket de compra ni una factura simplificada.",
                    "en": "The image does not look like a receipt or a simplified invoice."},
    # pdf-a-audio (9.3 y 6.4): «tts_chars:25000>20000» son los caracteres que se leerían y el máximo por tarea del plan.
    "tts_chars": {"es": "Tu plan permite leer {max} caracteres por tarea y las páginas elegidas tienen {need}: elige un rango de páginas más corto.",
                  "en": "Your plan allows {max} characters per task and the selected pages have {need}: choose a shorter page range."},
    "tts_account": {"es": "PDF a audio necesita una cuenta: inicia sesión o regístrate gratis.",
                    "en": "PDF to audio needs an account: sign in or sign up for free."},
    "tts_voice_es": {"es": "La lectura en español aún no está disponible. Si el documento está en inglés, elige ese idioma.",
                     "en": "Reading in Spanish is not available yet. If the document is in English, choose that language."},
    "tts_voice_en": {"es": "La lectura en inglés no está disponible ahora mismo.", "en": "Reading in English is not available right now."},
    "tts_language": {"es": "El texto no parece estar en español ni en inglés, los dos idiomas que se pueden leer.",
                     "en": "The text does not seem to be in Spanish or English, the two languages that can be read."},
    "tts_count": {"es": "Este PDF tiene demasiado texto o es demasiado complejo para preparar su lectura a tiempo: divídelo antes con «Dividir PDF».",
                  "en": "This PDF has too much text or is too complex to prepare for reading in time: split it first with “Split PDF”."},
    "tts_empty": {"es": "No hay texto que leer en las páginas elegidas.", "en": "There is no text to read in the selected pages."},
    # Facturas electrónicas (F4-D2): «invoice_syntax:ubl>facturae» es la sintaxis del archivo y la de la página.
    "invoice_syntax": {"es": "Esta página convierte otra sintaxis de factura (el archivo es de otra): usa «Factura electrónica a PDF», que admite UBL, CII y Facturae.",
                       "en": "This page converts another invoice syntax: use “E-invoice to PDF”, which accepts UBL, CII and Facturae."},
    "invoice_xsd_invalid": {"es": "La factura no cumple el esquema oficial de UBL 2.1 o CII D16B: compruébala antes con «Validar factura electrónica».",
                            "en": "The invoice does not meet the official UBL 2.1 or CII D16B schema: check it first with “Validate e-invoice”."},
    "facturae_xsd_invalid": {"es": "La factura Facturae no cumple su esquema oficial: compruébala antes con «Validar factura electrónica».",
                             "en": "The Facturae invoice does not meet its official schema: check it first with “Validate e-invoice”."},
    "not_invoice": {"es": "El archivo no es una factura UBL, CII ni Facturae.", "en": "The file is not a UBL, CII or Facturae invoice."},
    # Sello de la plataforma (firmar-pdf, 10 y D-188).
    "share_account": {"es": "Para compartir con un enlace hace falta una cuenta: inicia sesión o regístrate gratis.",
                      "en": "Sharing with a link needs an account: sign in or sign up for free."},
    "share_hours": {"es": "Con tu plan el enlace puede durar como mucho {max} horas.", "en": "With your plan the link can last at most {max} hours."},
    "seal_account": {"es": "El sello de la plataforma necesita una cuenta: inicia sesión o regístrate gratis.",
                     "en": "The platform seal needs an account: sign in or sign up for free."},
    "seal_disabled": {"es": "El sello de la plataforma está apagado ahora mismo.", "en": "The platform seal is switched off right now."},
    "seal_config": {"es": "El sello de la plataforma no está disponible ahora mismo.", "en": "The platform seal is not available right now."},
    "seal_tsa": {"es": "No se ha podido obtener el sello de tiempo: vuelve a probar en unos minutos.",
                 "en": "The time stamp could not be obtained: try again in a few minutes."},
    "seal_account_limit": {"es": "Has usado hoy todos los sellos de la plataforma de tu cuenta: vuelve a probar mañana.",
                           "en": "You have used all of your account's platform seals for today: try again tomorrow."},
    "seal_revinfo": {"es": "No se ha podido comprobar la revocación del sello para el nivel B-LT: vuelve a probar en unos minutos.",
                     "en": "The seal's revocation could not be checked for level B-LT: try again in a few minutes."},
    "own_chain_invalid": {"es": "No se ha podido leer el certificado del archivo .p12 o .pfx.", "en": "The certificate in the .p12 or .pfx file could not be read."},
    "own_key_unsupported": {"es": "El certificado usa un tipo de clave que no se admite (solo RSA y EC).", "en": "The certificate uses an unsupported key type (only RSA and EC)."},
    "own_cert_expired": {"es": "El certificado está caducado o todavía no es válido.", "en": "The certificate has expired or is not valid yet."},
    "own_state_invalid": {"es": "La firma preparada no coincide con el PDF: vuelve a empezar la firma.", "en": "The prepared signature does not match the PDF: start signing again."},
    "own_signature_invalid": {"es": "La firma no corresponde a la clave del certificado: revisa el archivo .p12 y la contraseña.",
                              "en": "The signature does not match the certificate key: check the .p12 file and its password."},
    "own_output_invalid": {"es": "La firma resultante no se ha podido comprobar.", "en": "The resulting signature could not be checked."},
    "own_key_usage": {"es": "El certificado no sirve para firmar (su uso de clave no incluye la firma digital).",
                      "en": "The certificate cannot be used to sign (its key usage does not include digital signature)."},
    "own_revinfo": {"es": "No se ha podido consultar la revocación de tu certificado: vuelve a intentarlo o elige B-T.",
                    "en": "The revocation of your certificate could not be checked: try again or choose B-T."},
    "own_chain_path": {"es": "No se ha podido completar la cadena de tu certificado hasta su raíz: expórtalo con la cadena completa.",
                       "en": "Your certificate chain could not be completed up to its root: export it with the full chain."},
    "own_one_file": {"es": "Con certificado propio se firma un PDF cada vez.", "en": "With your own certificate, one PDF is signed at a time."},
    "seal_field_missing": {"es": "El PDF no tiene un campo de firma con ese nombre.", "en": "The PDF has no signature field with that name."},
    "seal_field_signed": {"es": "Ese campo de firma ya está firmado: elige otro o crea uno nuevo.",
                          "en": "That signature field is already signed: choose another one or create a new one."},
    "seal_locked": {"es": "El documento está certificado sin permitir cambios: no se le puede añadir otra firma sin invalidarlo.",
                    "en": "The document is certified with no changes allowed: another signature cannot be added without invalidating it."},
    "seal_certify_signed": {"es": "Solo se puede certificar un documento sin firmas: quita la certificación o usa el original sin firmar.",
                            "en": "Only an unsigned document can be certified: turn off certification or use the unsigned original."},
    "seal_lta_existing": {"es": "El documento ya tiene sellos de tiempo de documento: elige el nivel B-LT.",
                          "en": "The document already has document time stamps: choose level B-LT."},
    "seal_image": {"es": "La imagen de la firma no es válida: vuelve a dibujarla o a escribirla.", "en": "The signature image is not valid: draw or type it again."},
    "seal_invalid": {"es": "El sello no se ha podido completar correctamente.", "en": "The seal could not be completed correctly."},
    "seal_size": {"es": "Para el sello, el PDF puede tener hasta {max} MB y este tiene {need} MB.",
                  "en": "For the seal, the PDF can be up to {max} MB and this one is {need} MB."},
    "seal_limit": {"es": "Se ha alcanzado el número de sellos de la plataforma de hoy: vuelve a probar mañana.",
                   "en": "Today's number of platform seals has been reached: try again tomorrow."},
    # solicitar-firmas (F4-C2, D-202): «request_*» del propietario y «sign_*» del firmante.
    "request_stage": {"es": "Esa fase la crea la propia solicitud de firmas, no la página.", "en": "That step is created by the signature request itself, not by the page."},
    "request_account": {"es": "Pedir firmas necesita una cuenta: inicia sesión o regístrate gratis.", "en": "Requesting signatures needs an account: sign in or sign up for free."},
    "request_email": {"es": "Hace falta un correo verificado para pedir firmas.", "en": "You need a verified email address to request signatures."},
    "request_no_signers": {"es": "Añade al menos un firmante.", "en": "Add at least one signer."},
    "request_signers": {"es": "Con tu plan puedes pedir la firma a {max} personas como mucho.", "en": "With your plan you can ask up to {max} people to sign."},
    "request_duplicate_email": {"es": "Cada firmante necesita un correo distinto.", "en": "Each signer needs a different email address."},
    "request_encrypted": {"es": "El PDF está protegido con contraseña: quítasela antes con «Desbloquear PDF».",
                          "en": "The PDF is password-protected: remove the password first with “Unlock PDF”."},
    "request_field_repeated": {"es": "Cada firmante necesita su propio campo de firma.", "en": "Each signer needs their own signature field."},
    "request_field_taken": {"es": "El PDF ya tiene un campo llamado «{need}»: elígelo para un firmante o cámbiale el nombre.",
                            "en": "The PDF already has a field called “{need}”: choose it for a signer or rename it."},
    "request_signed_needs_fields": {"es": "El PDF ya está firmado: solo se pueden usar sus campos de firma vacíos, porque una página nueva invalidaría las firmas.",
                                    "en": "The PDF is already signed: only its empty signature fields can be used, because a new page would invalidate the signatures."},
    "request_job": {"es": "El documento preparado ya no está disponible: vuelve a prepararlo.", "en": "The prepared document is no longer available: prepare it again."},
    "request_mismatch": {"es": "Los firmantes no coinciden con los del documento preparado: vuelve a prepararlo.",
                         "en": "The signers do not match the prepared document: prepare it again."},
    "request_limit": {"es": "Has llegado al número de solicitudes de firma de hoy ({max}): vuelve mañana.",
                      "en": "You have reached today's number of signature requests ({max}): come back tomorrow."},
    "request_open": {"es": "Tienes {max} solicitudes de firma abiertas, el máximo de tu plan: espera a que terminen o cancela alguna.",
                     "en": "You have {max} open signature requests, your plan's maximum: wait for them to finish or cancel one."},
    "request_recipient": {"es": "Uno de los destinatarios ya ha recibido hoy demasiadas solicitudes de firma: prueba mañana.",
                          "en": "One of the recipients has already received too many signature requests today: try tomorrow."},
    "request_finalizing": {"es": "Ya han firmado todos y se está sellando el documento: podrás borrarla cuando termine.",
                           "en": "Everyone has signed and the document is being sealed: you can delete it when it finishes."},
    "request_closed": {"es": "Esta solicitud ya está cerrada.", "en": "This request is already closed."},
    "request_image": {"es": "La imagen de la firma no es válida: dibújala o escríbela otra vez.", "en": "The signature image is not valid: draw or type it again."},
    "request_inputs": {"es": "Faltan el documento o la imagen de la firma.", "en": "The document or the signature image is missing."},
    "sign_link": {"es": "El enlace no es válido o se ha sustituido por uno más reciente: usa el del último correo que te hayamos enviado.",
                  "en": "The link is not valid or has been replaced by a newer one: use the one in the latest email we sent you."},
    "sign_closed": {"es": "Esta solicitud de firma ya está cerrada.", "en": "This signature request is already closed."},
    "sign_not_now": {"es": "Ahora no puedes firmar: ya lo has hecho o todavía no es tu turno.", "en": "You cannot sign right now: you already did or it is not your turn yet."},
    "sign_code_expired": {"es": "El código ha caducado o no se ha pedido: pide uno nuevo.", "en": "The code has expired or was not requested: ask for a new one."},
    "sign_code_invalid": {"es": "El código no es correcto.", "en": "The code is not correct."},
    "sign_code_locked": {"es": "Demasiados intentos con este código: pide uno nuevo.", "en": "Too many attempts with this code: ask for a new one."},
    "sign_code_rate": {"es": "Has pedido demasiados códigos: espera un rato y vuelve a probar.", "en": "You have asked for too many codes: wait a while and try again."},
    # crear-factura-electronica (F4-E2, D-205): lo que pide cada formato y el veredicto del validador.
    "einvoice_invalid": {"es": "El validador rechaza la factura generada ({need}); no se entrega. Revisa los datos y vuelve a probar.",
                         "en": "The validator rejects the generated invoice ({need}); it is not delivered. Check the details and try again."},
    "einvoice_lines": {"es": "Añade al menos un concepto, cada uno con su descripción.", "en": "Add at least one item, each with its description."},
    "einvoice_pdfa_fonts": {"es": "El PDF tiene fuentes sin incrustar y no se puede pasar a PDF/A sin Ghostscript, que no usamos: expórtalo de nuevo desde tu programa con las fuentes incrustadas.",
                            "en": "The PDF has fonts that are not embedded and cannot be made PDF/A without Ghostscript, which we do not use: export it again from your program with embedded fonts."},
    "einvoice_signed_pdf": {"es": "El PDF está firmado digitalmente y convertirlo a PDF/A invalidaría la firma: usa la versión sin firmar.",
                            "en": "The PDF is digitally signed and converting it to PDF/A would invalidate the signature: use the unsigned version."},
    "einvoice_pdf_password": {"es": "El PDF está protegido con contraseña: quítasela antes con «Desbloquear PDF».",
                              "en": "The PDF is password-protected: remove the password first with “Unlock PDF”."},
    "pandoc_memory": {"es": "El documento es demasiado grande o complejo para convertirlo.", "en": "The document is too large or complex to convert."},
    "zip_no_document": {"es": "El ZIP no contiene ningún documento de ese tipo.", "en": "The ZIP does not contain any document of that type."},
    "data_too_deep": {"es": "Los datos están anidados a demasiada profundidad (más de 200 niveles).", "en": "The data is nested too deeply (more than 200 levels)."},
    "data_too_big": {"es": "Los datos tienen demasiados valores (más de 5 millones, contando los alias de YAML expandidos).",
                     "en": "The data has too many values (more than 5 million, counting expanded YAML aliases)."},
    "data_output_too_big": {"es": "El resultado pasaría de 200 MB: divide los datos en archivos más pequeños.",
                            "en": "The result would exceed 200 MB: split the data into smaller files."},
    "data_cycle": {"es": "Los datos se contienen a sí mismos (un alias de YAML que apunta a su propio nodo) y no se pueden pasar a JSON.",
                   "en": "The data contains itself (a YAML alias pointing to its own node) and cannot be turned into JSON."},
    "xml_entities": {"es": "El XML declara entidades o carga un DTD externo, que no se admiten por seguridad.",
                     "en": "The XML declares entities or loads an external DTD, which are not allowed for security reasons."},
    "csv_wrong_encoding": {"es": "El archivo no está en la codificación elegida: prueba con «Detectar».",
                           "en": "The file is not in the chosen encoding: try “Detect”."},
    "font_variable": {"es": "Es una fuente variable: se puede pasar a WOFF2 y desde él, pero no entre TTF y OTF.",
                      "en": "It is a variable font: it can be converted to and from WOFF2, but not between TTF and OTF."},
    "cms_not_signed": {"es": "El archivo no es una firma CAdES ni PKCS#7 (no contiene datos firmados).",
                       "en": "The file is not a CAdES or PKCS#7 signature (it holds no signed data)."},
    "cms_detached": {"es": "Es una firma separada: el documento no va dentro. Para comprobarla, sube la firma y el documento a Verificar firma.",
                     "en": "It is a detached signature: the document is not inside. To check it, upload the signature and the document to Verify signature."},
    "cms_detached_needs_original": {"es": "Es una firma separada: sube también el documento que se firmó.",
                                    "en": "It is a detached signature: upload the signed document too."},
    "cms_nesting": {"es": "La firma está anidada más de 5 veces.", "en": "The signature is nested more than 5 times."},
    "xades_no_signature": {"es": "El XML no tiene ninguna firma XAdES ni XMLDSig.", "en": "The XML has no XAdES or XMLDSig signature."},
    "xades_detached": {"es": "La firma apunta a un documento que no va dentro: súbelo junto a la firma en Verificar firma.",
                       "en": "The signature points to a document that is not inside: upload it with the signature to Verify signature."},
    "verify_two_files": {"es": "Con dos archivos, uno debe ser la firma (.csig, .p7m, .p7s o .xsig) y el otro, el documento firmado.",
                         "en": "With two files, one must be the signature (.csig, .p7m, .p7s or .xsig) and the other the signed document."},
    "geo_too_many_points": {"es": "El mapa tiene más de 2 millones de puntos.", "en": "The map has more than 2 million points."},
    "geo_empty": {"es": "El archivo no tiene ningún punto, línea ni polígono válido.", "en": "The file has no valid point, line or polygon."},
    "geo_no_columns": {"es": "No se encuentran las columnas de latitud y longitud: indícalas en las opciones avanzadas.",
                       "en": "The latitude and longitude columns were not found: set them in the advanced options."},
    "shp_not_shapefile": {"es": "El ZIP trae un archivo con extensión de Shapefile que no lo es.", "en": "The ZIP holds a file with a Shapefile extension that is not one."},
    "kmz_no_kml": {"es": "El KMZ no contiene ningún archivo KML.", "en": "The KMZ does not contain any KML file."},
    "shp_incomplete": {"es": "El ZIP no tiene un Shapefile completo: hacen falta al menos el .shp, el .shx y el .dbf.",
                       "en": "The ZIP has no complete Shapefile: at least the .shp, .shx and .dbf are needed."},
    "xades_duplicate_ids": {"es": "El XML repite un identificador (Id): no se puede saber qué parte es la firmada, así que no se extrae.",
                            "en": "The XML repeats an identifier (Id): it is impossible to tell which part is the signed one, so nothing is extracted."},
    "xades_ambiguous": {"es": "Las firmas válidas del XML apuntan a documentos distintos: no se puede saber cuál extraer.",
                        "en": "The valid signatures in the XML point to different documents: it is impossible to tell which one to extract."},
    "xades_detached_needs_original": {"es": "La firma apunta a un documento que va aparte: súbelo junto a la firma.",
                                      "en": "The signature points to a separate document: upload it together with the signature."},
    "verify_attached_mismatch": {"es": "La firma ya lleva el documento dentro y el segundo archivo no es ese documento (o no se usa): sube solo la firma.",
                                 "en": "The signature already contains the document and the second file is not that document (or is not used): upload only the signature."},
    "verify_no_signature": {"es": "Sube una firma (.csig, .p7m, .p7s, .xsig o un XML o PDF firmado) y, si va separada, el documento.",
                            "en": "Upload a signature (.csig, .p7m, .p7s, .xsig or a signed XML or PDF) and, if it is detached, the document."},
    "mail_empty": {"es": "El buzón no tiene ningún mensaje.", "en": "The mailbox has no messages."},
    "mail_too_many": {"es": "El buzón tiene más de 20 000 mensajes: divídelo antes.", "en": "The mailbox has more than 20,000 messages: split it first."},
    "agenda_empty": {"es": "El archivo no tiene ningún contacto o evento.", "en": "The file has no contacts or events."},
    "agenda_too_many": {"es": "El archivo tiene más de 100 000 contactos o eventos.", "en": "The file has more than 100,000 contacts or events."},
    "ics_no_columns": {"es": "El CSV necesita al menos una columna de título (Asunto, Título o Subject) y otra de fecha de inicio.",
                       "en": "The CSV needs at least a title column (Subject, Title or Summary) and a start date column."},
    "archive_format": {"es": "No es un comprimido del tipo que admite esta herramienta (o es un .gz suelto, no un .tar.gz).",
                       "en": "It is not an archive of the kind this tool accepts (or it is a plain .gz, not a .tar.gz)."},
    "archive_empty": {"es": "El archivo comprimido está vacío o dañado.", "en": "The archive is empty or damaged."},
    "archive_password": {"es": "El archivo comprimido está protegido: escribe su contraseña.", "en": "The archive is protected: enter its password."},
    "archive_password_or_cipher": {"es": "La contraseña no es correcta o el cifrado de este ZIP no se admite.",
                                   "en": "The password is wrong or this ZIP's encryption is not supported."},
    "archive_encrypted_unsupported": {"es": "Los RAR y 7z cifrados no se pueden abrir aquí: descomprímelo en tu equipo con su contraseña.",
                                      "en": "Encrypted RAR and 7z archives cannot be opened here: extract it on your computer with its password."},
    "pdf_not_invoice": {"es": "El PDF no parece una factura.", "en": "The PDF does not look like an invoice."},
    "einvoice_quantity": {"es": "Ningún concepto puede tener cantidad 0.", "en": "No item can have quantity 0."},
    "einvoice_names": {"es": "Faltan el nombre del emisor o el del cliente.", "en": "The seller's or the buyer's name is missing."},
    "einvoice_country": {"es": "«{need}» no es un código de país admitido (ISO 3166-1, como ES o FR; Grecia es GR).",
                         "en": "“{need}” is not a supported country code (ISO 3166-1, such as ES or FR; Greece is GR)."},
    "einvoice_exchange_rate": {"es": "Con otra moneda hace falta el tipo de cambio a euros: la cuota de IVA va también en euros.",
                               "en": "With another currency the exchange rate to euros is required: the VAT amount is also given in euros."},
    "einvoice_iban": {"es": "Con pago por transferencia hace falta el IBAN donde se cobra.", "en": "Payment by credit transfer needs the IBAN to be paid into."},
    "einvoice_payment": {"es": "XRechnung pide la forma de pago.", "en": "XRechnung needs the payment means."},
    "einvoice_payment_unsupported": {"es": "Esa forma de pago (adeudo o, en XRechnung, tarjeta) pide datos que este formulario no tiene: elige transferencia o efectivo.",
                                     "en": "That payment means (direct debit or, in XRechnung, card) needs data this form does not have: choose credit transfer or cash."},
    "einvoice_buyer_vat": {"es": "Con inversión del sujeto pasivo o entrega intracomunitaria hace falta el NIF-IVA del cliente.",
                           "en": "Reverse charge or an intra-Community supply needs the buyer's VAT ID."},
    "einvoice_delivery_date": {"es": "Una entrega intracomunitaria necesita la fecha de la operación.", "en": "An intra-Community supply needs the date of supply."},
    "einvoice_mixed_o": {"es": "Una factura de operaciones no sujetas no puede llevar conceptos con IVA.", "en": "An invoice for supplies not subject to VAT cannot have items with VAT."},
    "einvoice_facturae_field": {"es": "Facturae no admite el valor de «{need}» (falta o es demasiado largo para su esquema): corrígelo; no lo recortamos.",
                                "en": "Facturae does not accept the value of “{need}” (missing or too long for its schema): fix it; we do not cut it."},
    "einvoice_dir3": {"es": "Para FACe hacen falta los tres códigos DIR3: oficina contable, órgano gestor y unidad tramitadora.",
                      "en": "FACe needs all three DIR3 codes: accounting office, managing body and processing unit."},
    "einvoice_number": {"es": "Falta el número de factura.", "en": "The invoice number is missing."},
    "einvoice_surcharge": {"es": "El recargo de equivalencia solo existe en Facturae: elige Facturae o quítalo.",
                           "en": "The equivalence surcharge only exists in Facturae: choose Facturae or remove it."},
    "einvoice_irpf": {"es": "La retención de IRPF solo existe en Facturae: elige Facturae o quítala.",
                      "en": "Income tax withholding only exists in Facturae: choose Facturae or remove it."},
    "einvoice_buyer_reference": {"es": "Este formato pide la referencia del comprador (en XRechnung, el Leitweg-ID) o, en Peppol, la del pedido.",
                                 "en": "This format needs the buyer reference (in XRechnung, the Leitweg-ID) or, in Peppol, the order reference."},
    "einvoice_seller_contact": {"es": "XRechnung pide la persona de contacto, el teléfono y el correo del emisor.",
                                "en": "XRechnung needs the seller's contact person, phone and email."},
    "einvoice_address": {"es": "XRechnung pide el código postal y la población del emisor y del cliente.",
                         "en": "XRechnung needs the seller's and buyer's postcode and city."},
    "einvoice_endpoint": {"es": "Este formato pide la dirección electrónica (Peppol) del emisor y del cliente.",
                          "en": "This format needs the seller's and buyer's electronic (Peppol) address."},
    "einvoice_endpoint_scheme": {"es": "Peppol no admite el correo («EM») como dirección electrónica: usa un esquema EAS, como 9920 para un NIF español.",
                                 "en": "Peppol does not accept email («EM») as an electronic address: use an EAS scheme, such as 9920 for a Spanish NIF."},
    "einvoice_exemption": {"es": "Con IVA del 0 % hace falta la causa de la exención.", "en": "With 0 % VAT the exemption reason is required."},
    "einvoice_facturae_nif": {"es": "Facturae pide el NIF del emisor y del cliente.", "en": "Facturae needs the seller's and buyer's tax ID."},
    "einvoice_facturae_currency": {"es": "Esta versión genera Facturae solo en euros.", "en": "This version only generates Facturae in euros."},
    "einvoice_seller_vat": {"es": "Falta el NIF del emisor.", "en": "The seller's tax ID is missing."},
    # verificar-firmas-pdf (D-186): «sig_count:60>50» son las firmas y sellos del documento y el máximo.
    "sig_count": {"es": "El documento tiene {need} firmas y sellos de tiempo; se pueden verificar {max} como máximo.",
                  "en": "The document has {need} signatures and time stamps; at most {max} can be verified."},
    # PDF/A y PDF/UA desde Office o HTML (D-182): el rango lo aplica el motor, en el orden del documento.
    "range_order": {"es": "Con PDF/A o PDF/UA las páginas salen en el orden del documento: escribe el rango de menor a mayor "
                          "y, si necesitas otro orden, usa después «Organizar PDF».",
                    "en": "With PDF/A or PDF/UA the pages come out in document order: write the range from lowest to highest "
                          "and, if you need another order, use “Organize PDF” afterwards."},
    "range_slides": {"es": "Con PDF/A o PDF/UA, el rango de páginas no se puede combinar con las páginas de notas ni con las "
                           "diapositivas ocultas: convierte todas las páginas o quita esas opciones.",
                     "en": "With PDF/A or PDF/UA, a page range cannot be combined with notes pages or hidden slides: convert "
                           "all pages or turn those options off."},
    "ai_scanned": {"es": "Las páginas {pages} son imágenes sin texto: activa «Leer las páginas escaneadas» o pasa antes OCR PDF.",
                   "en": "Pages {pages} are images without text: turn on “Read scanned pages” or run OCR PDF first."},
}
RESET = {"es": "Vuelve a partir de las {reset} (hora de Madrid).", "en": "Try again after {reset} (Madrid time)."}


def message(code: str, locale: str = "es", detail: str | None = None, reset: str | None = None) -> str:
    lang = "en" if locale.startswith("en") else "es"
    text = MESSAGES.get(code, MESSAGES["INTERNAL"])[lang]
    if detail and ":" in detail:
        key, _, values = detail.partition(":")
        if key in DETAILS:
            need, _, top = values.partition(">")
            try:
                return DETAILS[key][lang].format(need=need, max=top, pages=values)
            except (KeyError, IndexError):
                pass
    elif detail in DETAILS:
        return DETAILS[detail][lang]
    if code == "AI_BUDGET_EXHAUSTED" and reset:
        text = f"{text} {RESET[lang].format(reset=reset)}"
    return text


class AppError(Exception):
    """Error con código estable que la API traduce y devuelve."""

    def __init__(self, code: ErrorCode | str, status: int = 400, detail: str | None = None, extra: dict | None = None):
        super().__init__(f"{code}: {detail or ''}")
        self.code = str(code)
        self.status = status
        self.detail = detail
        self.extra = extra or {}


class ToolError(AppError):
    """Error de una herramienta durante el proceso; `transient` indica si merece reintento."""

    def __init__(self, code: ErrorCode | str, detail: str | None = None, transient: bool = False):
        super().__init__(code, status=422, detail=detail)
        self.transient = transient
