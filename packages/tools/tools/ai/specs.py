"""Especificaciones de las herramientas de IA (7.6 y 6.3). Sin motores: se importan en la API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.options import opt
from core.registry import AiSpec, ToolSpec

LANGUAGES = {
    "documento": ("El del documento", "The document's language"),
    "es": ("Español", "Spanish"), "en": ("Inglés", "English"), "fr": ("Francés", "French"), "de": ("Alemán", "German"),
    "it": ("Italiano", "Italian"), "pt": ("Portugués", "Portuguese"), "ca": ("Catalán", "Catalan"),
}
DOC_LANGUAGES = {
    "auto": ("Español o inglés", "Spanish or English"),
    "es": ("Español", "Spanish"), "en": ("Inglés", "English"), "fr": ("Francés", "French"), "de": ("Alemán", "German"),
    "it": ("Italiano", "Italian"), "pt": ("Portugués", "Portuguese"), "ca": ("Catalán", "Catalan"),
}


class DocumentoIAOptions(BaseModel):
    """Opciones comunes de las herramientas de IA que leen un PDF."""

    paginas: str = opt("todas", "Páginas", "Pages")
    ocr: bool = opt(True, "Leer las páginas escaneadas con OCR (cuenta como tarea pesada)",
                    "Read scanned pages with OCR (counts as a heavy task)", advanced=True)
    idioma_documento: Literal["auto", "es", "en", "fr", "de", "it", "pt", "ca"] = opt(
        "auto", "Idioma del documento (para el OCR)", "Document language (for OCR)", advanced=True, labels=DOC_LANGUAGES,
        show_if={"ocr": (True,)})


class ResumirOptions(DocumentoIAOptions):
    longitud: Literal["breve", "media", "detallada"] = opt(
        "media", "Extensión", "Length",
        labels={"breve": ("Breve (unas líneas)", "Short (a few lines)"), "media": ("Media", "Medium"),
                "detallada": ("Detallada (por apartados)", "Detailed (by section)")})
    estilo: Literal["puntos", "parrafos"] = opt(
        "puntos", "Estilo", "Style", labels={"puntos": ("Puntos clave", "Key points"), "parrafos": ("Párrafos", "Paragraphs")})
    idioma: Literal["documento", "es", "en", "fr", "de", "it", "pt", "ca"] = opt(
        "documento", "Idioma del resumen", "Summary language", labels=LANGUAGES)
    formato: Literal["docx", "txt", "md"] = opt(
        "docx", "Formato", "Format", labels={"docx": ("Word (DOCX)", "Word (DOCX)"), "txt": ("Texto (TXT)", "Text (TXT)"),
                                              "md": ("Markdown", "Markdown")})


def ai_tool(slug_es, slug_en, name_es, name_en, options, impl, summary_es, summary_en, ai: AiSpec, **kw) -> ToolSpec:
    return ToolSpec(slug_es=slug_es, slug_en=slug_en, name_es=name_es, name_en=name_en, category="ai", where="server",
                    inputs=kw.pop("inputs", ("pdf",)), outputs=kw.pop("outputs", ("docx", "txt", "md")), options=options,
                    worker_group="ai", cost_class="ai", impl=impl, launch=True, phase="F3", max_files=1,
                    time_limit=kw.pop("time_limit", 1800), summary_es=summary_es, summary_en=summary_en, ai=ai, **kw)


class ChatOptions(DocumentoIAOptions):
    """chat-pdf: las mismas que cualquier herramienta que lee un PDF (páginas y OCR)."""


class PreguntasOptions(DocumentoIAOptions):
    numero: int = opt(10, "Número de preguntas", "Number of questions", ge=3, le=40)
    tipo: Literal["test", "verdadero_falso", "corta", "mezcla"] = opt(
        "test", "Tipo de pregunta", "Question type",
        labels={"test": ("Test (opción múltiple)", "Multiple choice"), "verdadero_falso": ("Verdadero o falso", "True or false"),
                "corta": ("Respuesta corta", "Short answer"), "mezcla": ("Mezcla de los tres", "A mix of the three")})
    opciones: int = opt(4, "Opciones por pregunta", "Options per question", ge=3, le=5, show_if={"tipo": ("test", "mezcla")})
    dificultad: Literal["facil", "media", "dificil"] = opt(
        "media", "Dificultad", "Difficulty", labels={"facil": ("Fácil", "Easy"), "media": ("Media", "Medium"), "dificil": ("Difícil", "Hard")})
    idioma: Literal["documento", "es", "en", "fr", "de", "it", "pt", "ca"] = opt(
        "documento", "Idioma de las preguntas", "Language of the questions", labels=LANGUAGES)
    formato: Literal["docx", "gift", "txt"] = opt(
        "docx", "Formato", "Format", labels={"docx": ("Word (examen para imprimir)", "Word (printable exam)"),
                                              "gift": ("Moodle (GIFT)", "Moodle (GIFT)"), "txt": ("Texto (TXT)", "Text (TXT)")})
    soluciones: Literal["final", "aparte", "no"] = opt(
        "final", "Soluciones", "Answers", show_if={"formato": ("docx", "txt")},
        labels={"final": ("Al final", "At the end"), "aparte": ("En otro archivo", "In a separate file"), "no": ("Sin soluciones", "No answers")})


class FichasOptions(DocumentoIAOptions):
    numero: int = opt(20, "Número de fichas", "Number of cards", ge=5, le=100)
    tipo: Literal["concepto", "pregunta"] = opt(
        "concepto", "Tipo de ficha", "Card type", labels={"concepto": ("Término y definición", "Term and definition"),
                                                          "pregunta": ("Pregunta y respuesta", "Question and answer")})
    idioma: Literal["documento", "es", "en", "fr", "de", "it", "pt", "ca"] = opt(
        "documento", "Idioma de las fichas", "Language of the cards", labels=LANGUAGES)
    formato: Literal["tsv", "csv", "docx"] = opt(
        "tsv", "Formato", "Format", labels={"tsv": ("Anki o Quizlet (TXT con tabuladores)", "Anki or Quizlet (tab-separated TXT)"),
                                             "csv": ("CSV (Excel)", "CSV (Excel)"), "docx": ("Word (para imprimir y recortar)", "Word (to print and cut out)")})


class PresentacionOptions(DocumentoIAOptions):
    diapositivas: int = opt(10, "Número de diapositivas (con la portada)", "Number of slides (including the cover)", ge=4, le=30)
    estilo: Literal["claro", "oscuro", "color"] = opt(
        "claro", "Estilo", "Style", labels={"claro": ("Claro", "Light"), "oscuro": ("Oscuro", "Dark"), "color": ("Cálido", "Warm")})
    notas: bool = opt(True, "Notas del orador", "Speaker notes")
    idioma: Literal["documento", "es", "en", "fr", "de", "it", "pt", "ca"] = opt(
        "documento", "Idioma de la presentación", "Presentation language", labels=LANGUAGES)


TARGETS = {k: v for k, v in {
    "es": ("Español", "Spanish"), "en": ("Inglés", "English"), "fr": ("Francés", "French"), "de": ("Alemán", "German"),
    "it": ("Italiano", "Italian"), "pt": ("Portugués", "Portuguese"), "ca": ("Catalán", "Catalan"), "nl": ("Neerlandés", "Dutch"),
    "pl": ("Polaco", "Polish"), "ro": ("Rumano", "Romanian"), "gl": ("Gallego", "Galician"), "eu": ("Euskera", "Basque"),
}.items()}
Target = Literal["es", "en", "fr", "de", "it", "pt", "ca", "nl", "pl", "ro", "gl", "eu"]


class TraducirOptions(DocumentoIAOptions):
    destino: Target = opt("en", "Traducir al", "Translate into", labels=TARGETS)
    origen: Literal["auto", "es", "en", "fr", "de", "it", "pt", "ca", "nl", "pl", "ro", "gl", "eu"] = opt(
        "auto", "Idioma del original", "Original language", advanced=True, labels={"auto": ("Detectarlo", "Detect it"), **TARGETS})
    formato: Literal["docx_pdf", "docx", "pdf"] = opt(
        "docx_pdf", "Formato", "Format", labels={"docx_pdf": ("Word y PDF", "Word and PDF"), "docx": ("Word (DOCX)", "Word (DOCX)"),
                                                  "pdf": ("PDF", "PDF")})
    glosario: str = opt("", "Términos que no se traducen (uno por línea)", "Terms not to translate (one per line)",
                        advanced=True, widget="textarea", max_length=1000)


SPECS: list[ToolSpec] = [
    ai_tool("resumir-pdf", "summarize-pdf", "Resumir PDF", "Summarize PDF", ResumirOptions, "tools.ai.resumir:run",
            "Resume un PDF con IA: puntos clave o párrafos, en el idioma que elijas.",
            "Summarize a PDF with AI: key points or paragraphs, in the language you choose.",
            # 6.3: 1 petición si cabe en el contexto; si no, 1 por bloque y 1 final (el resto se reserva al leer el texto).
            AiSpec(estimate=lambda o: 1, min_context=8000, min_output=1500),
            related=("pdf-a-txt", "ocr-pdf", "pdf-a-word")),
    # 6.3: preparar no llama al modelo (0 peticiones); cada pregunta reserva 1 en POST /v1/ai/chat.
    ai_tool("chat-pdf", "chat-with-pdf", "Chat con PDF", "Chat with PDF", ChatOptions, "tools.ai.chat:prepare",
            "Pregunta lo que quieras sobre un PDF: responde con lo que dice el documento y te indica las páginas.",
            "Ask anything about a PDF: answers come from the document and tell you which pages.",
            AiSpec(estimate=lambda o: 0, min_context=8000, min_output=900), outputs=(), queue_kind="embed",
            related=("resumir-pdf", "buscar-en-pdf", "pdf-a-txt")),
    # 6.3: 1 petición si el documento cabe; el worker reserva las de cada bloque (y las de varias tandas si no caben en la
    # salida máxima del modelo) antes de empezar.
    ai_tool("generador-de-preguntas", "question-generator", "Generador de preguntas", "Question generator", PreguntasOptions,
            "tools.ai.generador:run", "Crea preguntas de examen sobre un PDF, con soluciones, en Word, Moodle o texto.",
            "Create exam questions from a PDF, with answers, in Word, Moodle or text.",
            AiSpec(estimate=lambda o: 1, json=True, min_context=8000, min_output=1500), outputs=("docx", "txt"),
            related=("pdf-a-fichas", "resumir-pdf", "chat-pdf")),
    ai_tool("pdf-a-fichas", "pdf-to-flashcards", "PDF a fichas", "PDF to flashcards", FichasOptions, "tools.ai.fichas:run",
            "Convierte un PDF en fichas de estudio para Anki o Quizlet, CSV o Word.",
            "Turn a PDF into study flashcards for Anki or Quizlet, CSV or Word.",
            AiSpec(estimate=lambda o: 1, json=True, min_context=8000, min_output=1500), outputs=("txt", "csv", "docx"),
            related=("generador-de-preguntas", "resumir-pdf", "chat-pdf")),
    # 6.3: 2 peticiones (esquema y diapositivas).
    ai_tool("pdf-a-presentacion", "pdf-to-presentation", "PDF a presentación", "PDF to presentation", PresentacionOptions,
            "tools.ai.presentacion:run", "Crea una presentación de PowerPoint a partir de un PDF, con notas del orador.",
            "Create a PowerPoint presentation from a PDF, with speaker notes.",
            AiSpec(estimate=lambda o: 2, json=True, min_context=8000, min_output=2000), outputs=("pptx",),
            related=("resumir-pdf", "pdf-a-ppt", "generador-de-preguntas")),
    # 6.3: 1 petición por lote de párrafos que quepa en la salida máxima del modelo.
    ai_tool("traducir-pdf", "translate-pdf", "Traducir PDF", "Translate PDF", TraducirOptions, "tools.ai.traducir:run",
            "Traduce un PDF a otro idioma y lo entrega en Word y PDF con una maquetación sencilla.",
            "Translate a PDF into another language and get it as Word and PDF with a simple layout.",
            AiSpec(estimate=lambda o: 1, json=True, min_context=8000, min_output=2000), outputs=("docx", "pdf"),
            related=("pdf-a-word", "resumir-pdf", "chat-pdf")),
]
