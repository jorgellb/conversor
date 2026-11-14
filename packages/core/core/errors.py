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
