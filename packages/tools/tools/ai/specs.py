"""Especificaciones de las herramientas de IA (7.6 y 6.3). Sin motores: se importan en la API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from core.options import opt
from core.registry import AiSpec, ToolSpec
from tools.av.specs import AUDIO_INPUTS, LANGUAGES as AUDIO_LANGUAGES, PRECISION, VIDEO_INPUTS, Language as AudioLanguage, parse_time
from tools.ocr.specs import IMAGE_INPUTS, _check_codes

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
                    worker_group=kw.pop("worker_group", "ai"), cost_class="ai", impl=impl, launch=True, phase=kw.pop("phase", "F3"),
                    max_files=kw.pop("max_files", 1),
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


DELIMITERS = {"coma": ("Coma (,)", "Comma (,)"), "punto_y_coma": ("Punto y coma (;), para Excel en español",
                                                                  "Semicolon (;), for Excel in Spanish"),
              "tabulador": ("Tabulador", "Tab")}


# Idiomas de Tesseract que instala la imagen worker-convert (workers/Dockerfile), donde corre imagen-a-excel; workerocr
# (imagen-a-texto, ocr-pdf y ticket-a-excel) tiene tesseract-ocr-all. Se comprueba al validar, antes de encolar (D-160).
CONVERT_LANGUAGES = ("spa", "eng", "cat", "eus", "glg", "fra", "deu", "ita", "por")


class ImagenExcelOptions(BaseModel):
    """imagen-a-excel (7.6): el Anexo A no fija opciones; las de D-160, con las hojas y los números de pdf-a-excel (A.9)."""

    formato: Literal["xlsx", "csv"] = opt("xlsx", "Formato", "Format",
                                         labels={"xlsx": ("Excel (XLSX)", "Excel (XLSX)"), "csv": ("CSV", "CSV")})
    hojas: Literal["una_por_tabla", "todas_en_una"] = opt(
        "una_por_tabla", "Hojas", "Sheets", show_if={"formato": ("xlsx",)},
        labels={"una_por_tabla": ("Una hoja por tabla", "One sheet per table"),
                "todas_en_una": ("Todas las tablas en una hoja", "All tables in one sheet")})
    delimitador: Literal["coma", "punto_y_coma", "tabulador"] = opt("coma", "Separador", "Delimiter", labels=DELIMITERS,
                                                                   show_if={"formato": ("csv",)})
    usar_ia: bool = opt(True, "Si no se reconoce la tabla, reconstruirla con IA (1 petición)",
                        "If the table is not recognised, rebuild it with AI (1 request)")
    numeros: bool = opt(True, "Convertir los números (1.234,56) en números de verdad", "Turn numbers (1,234.56) into real numbers",
                        advanced=True, show_if={"formato": ("xlsx",)})
    idiomas: list[str] = opt(["spa", "eng"], "Idiomas del OCR", "OCR languages", min_length=1, max_length=3, advanced=True)

    @field_validator("idiomas")
    @classmethod
    def _codes(cls, v: list[str]) -> list[str]:
        missing = [code for code in _check_codes(v) if code not in CONVERT_LANGUAGES]
        if missing:
            raise ValueError(f"Idiomas no disponibles en esta herramienta: {', '.join(missing)} (sí: {', '.join(CONVERT_LANGUAGES)})")
        return v


class TicketOptions(BaseModel):
    """ticket-a-excel (7.6): el Anexo A no fija opciones; las de D-163."""

    formato: Literal["xlsx", "csv"] = opt(
        "xlsx", "Formato", "Format", labels={"xlsx": ("Excel (XLSX, con una hoja de tickets y otra de conceptos)",
                                                       "Excel (XLSX, with a receipts sheet and an items sheet)"),
                                              "csv": ("CSV", "CSV")})
    filas: Literal["ticket", "concepto"] = opt(
        "ticket", "Filas del CSV", "CSV rows", show_if={"formato": ("csv",)},
        labels={"ticket": ("Una fila por ticket", "One row per receipt"), "concepto": ("Una fila por concepto", "One row per item")})
    delimitador: Literal["coma", "punto_y_coma", "tabulador"] = opt("punto_y_coma", "Separador", "Delimiter", labels=DELIMITERS,
                                                                   show_if={"formato": ("csv",)})
    idioma_ticket: Literal["auto", "es", "en", "fr", "de", "it", "pt", "ca"] = opt(
        "auto", "Idioma de los tickets (para el OCR)", "Receipt language (for OCR)", advanced=True, labels=DOC_LANGUAGES)


def _desde():
    return opt("0:00", "Desde (h:mm:ss)", "From (h:mm:ss)", advanced=True, max_length=20)


def _hasta():
    return opt("", "Hasta (vacío: hasta el final)", "To (empty: until the end)", advanced=True, max_length=20)


def _precision():
    return opt("normal", "Precisión de la transcripción (audio o vídeo)", "Transcription accuracy (audio or video)",
               labels=PRECISION, advanced=True)


class TramoOptions(BaseModel):
    """Comprobación del tramo de la grabación o de los subtítulos (F3-E, D-174 y D-175). Cada herramienta declara al
    final sus campos `desde`, `hasta` y `precision`, para que salgan los últimos en el formulario."""

    @field_validator("desde", "hasta", check_fields=False)
    @classmethod
    def _time(cls, v: str) -> str:
        parse_time(v)
        return v

    @model_validator(mode="after")
    def _span(self):
        start, end = parse_time(self.desde) or 0.0, parse_time(self.hasta)
        if end is not None and end <= start:
            raise ValueError("«Hasta» tiene que ir después de «Desde»")
        return self


SUBTITLE_INPUTS = ("srt", "vtt", "ass")


class TraducirSubtitulosOptions(TramoOptions):
    """traducir-subtitulos (7.10): el Anexo A no fija opciones; las de D-174."""

    destino: Target = opt("es", "Traducir al", "Translate into", labels=TARGETS)
    salida: Literal["mismo", "srt", "vtt"] = opt(
        "mismo", "Formato", "Format",
        labels={"mismo": ("El del original (SRT si subes audio o vídeo)", "Same as the original (SRT for audio or video)"),
                "srt": ("SRT", "SRT"), "vtt": ("WebVTT (VTT)", "WebVTT (VTT)")})
    bilingue: bool = opt(False, "Bilingüe: el original y debajo la traducción", "Bilingual: the original with the translation below")
    origen: Literal["auto", "es", "en", "fr", "de", "it", "pt", "ca", "nl", "pl", "ro", "gl", "eu"] = opt(
        "auto", "Idioma del original", "Original language", advanced=True, labels={"auto": ("Detectarlo", "Detect it"), **TARGETS})
    caracteres_por_linea: int = opt(42, "Caracteres por línea", "Characters per line", ge=30, le=60, advanced=True)
    glosario: str = opt("", "Términos que no se traducen (uno por línea)", "Terms not to translate (one per line)",
                        advanced=True, widget="textarea", max_length=1000)
    desde: str = _desde()
    hasta: str = _hasta()
    precision: Literal["normal", "alta"] = _precision()


MEETING_LANGUAGES = {"reunion": ("El de la reunión", "The meeting's language"),
                     **{k: v for k, v in LANGUAGES.items() if k != "documento"}}


class ResumirReunionOptions(TramoOptions):
    """resumir-reunion (7.10): el Anexo A no fija opciones; las de D-175."""

    idioma: AudioLanguage = opt("auto", "Idioma de la reunión", "Meeting language", labels=AUDIO_LANGUAGES)
    longitud: Literal["breve", "media", "detallada"] = opt(
        "media", "Extensión del resumen", "Summary length",
        labels={"breve": ("Breve (unas líneas)", "Short (a few lines)"), "media": ("Media", "Medium"),
                "detallada": ("Detallada (por temas)", "Detailed (by topic)")})
    idioma_resumen: Literal["reunion", "es", "en", "fr", "de", "it", "pt", "ca"] = opt(
        "reunion", "Idioma del resumen", "Summary language", labels=MEETING_LANGUAGES)
    temas: bool = opt(True, "Temas tratados", "Topics discussed")
    decisiones: bool = opt(True, "Decisiones", "Decisions")
    tareas: bool = opt(True, "Tareas, con responsable y fecha si se dicen", "Action items, with owner and date if mentioned")
    preguntas: bool = opt(True, "Preguntas abiertas", "Open questions")
    transcripcion: bool = opt(False, "Añadir la transcripción completa al final", "Add the full transcript at the end")
    formato: Literal["docx", "txt", "md"] = opt(
        "docx", "Formato", "Format", labels={"docx": ("Word (DOCX)", "Word (DOCX)"), "txt": ("Texto (TXT)", "Text (TXT)"),
                                              "md": ("Markdown", "Markdown")})
    desde: str = _desde()
    hasta: str = _hasta()
    precision: Literal["normal", "alta"] = _precision()


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
    # 6.3 no fija su coste: se reserva 1 petición al encolar y se devuelve si Docling reconoce la tabla en `workerconvert`
    # sin la IA (D-160). Con «usar IA» apagado no pide cuenta, consentimiento ni peticiones (D-161).
    ai_tool("imagen-a-excel", "image-to-excel", "Imagen a Excel", "Image to Excel", ImagenExcelOptions, "tools.ai.imagen_excel:run",
            "Pasa las tablas de una foto o una captura a Excel o CSV; si no se reconocen, las reconstruye con IA.",
            "Turn the tables in a photo or a screenshot into Excel or CSV; if they are not recognised, AI rebuilds them.",
            AiSpec(estimate=lambda o: 1, json=True, min_context=8000, min_output=2000, option="usar_ia"),
            inputs=IMAGE_INPUTS, outputs=("xlsx", "csv", "zip"), worker_group="convert",
            # Siempre pesada: Docling y Tesseract corren en `workerconvert` con la IA encendida o apagada (9.3); las
            # peticiones de IA van aparte, en su propio límite diario (D-161).
            cost=lambda o: "heavy",
            related=("pdf-a-excel", "imagen-a-texto", "ticket-a-excel")),
    # 6.3: 1 petición por ticket; la API reserva una por archivo al encolar (D-163). El OCR va antes en `workerocr`.
    ai_tool("ticket-a-excel", "receipt-to-excel", "Ticket a Excel", "Receipt to Excel", TicketOptions, "tools.ai.ticket:run",
            "Pasa tus tickets de compra a una hoja de Excel: comercio, fecha, conceptos, IVA y total, y avisa si no cuadran.",
            "Turn your shopping receipts into an Excel sheet: shop, date, items, tax and total, with a warning if they do not add up.",
            AiSpec(estimate=lambda o: 1, json=True, min_context=8000, min_output=1500, per_file=True),
            inputs=IMAGE_INPUTS, outputs=("xlsx", "csv"), worker_group="ocr", max_files=20,
            related=("imagen-a-excel", "imagen-a-texto", "pdf-a-excel")),
    # 6.3: 1 petición por bloque de cues que quepa en la salida máxima del modelo (un elemento JSON por cue). Los
    # subtítulos van directos a `ai`; el audio y el vídeo pasan antes por `av.heavy` (transcripción, cuenta como tarea
    # pesada) y vuelven. La API reserva 1; el worker reserva el resto antes de gastar (D-174).
    ai_tool("traducir-subtitulos", "translate-subtitles", "Traducir subtítulos", "Translate subtitles", TraducirSubtitulosOptions,
            "tools.ai.subtitulos:run",
            "Traduce subtítulos SRT, VTT o ASS a otro idioma conservando los tiempos; también crea y traduce los de un audio o un vídeo.",
            "Translate SRT, VTT or ASS subtitles into another language keeping their timings; it can also create and translate them from audio or video.",
            AiSpec(estimate=lambda o: 1, json=True, min_context=8000, min_output=2000),
            inputs=(*SUBTITLE_INPUTS, *AUDIO_INPUTS, *VIDEO_INPUTS), outputs=("srt", "vtt", "ass"), phase="F5", time_limit=4 * 3600,
            related=("video-a-subtitulos", "transcribir-audio", "traducir-pdf")),
    # 6.3: 1 petición si la transcripción cabe en el contexto; si no, 1 por bloque y 1 final (map-reduce). Empieza en
    # `av.heavy` (faster-whisper) y sigue en `ai`; siempre es tarea pesada por la transcripción (D-175).
    ai_tool("resumir-reunion", "summarize-meeting", "Resumir reunión", "Summarize meeting", ResumirReunionOptions,
            "tools.ai.reunion:run",
            "Resume la grabación de una reunión con IA: resumen, temas, decisiones, tareas con responsable y preguntas abiertas.",
            "Summarize a meeting recording with AI: summary, topics, decisions, action items with owners and open questions.",
            AiSpec(estimate=lambda o: 1, json=True, min_context=8000, min_output=1500),
            inputs=(*AUDIO_INPUTS, *VIDEO_INPUTS), outputs=("docx", "txt", "md"), worker_group="av", queue_kind="heavy",
            cost=lambda o: "heavy", phase="F5", time_limit=4 * 3600,
            related=("transcribir-audio", "resumir-pdf", "traducir-subtitulos")),
]
