"""Texto de un PDF preparado para leerlo en voz alta (pdf-a-audio, 7.6).

Solo biblioteca estándar: lo usan el worker `av` y la comprobación de la API antes de encolar (9.3: caracteres por
tarea), que lo ejecuta en un proceso aparte (`contar_texto.py`). Así los dos cuentan exactamente el mismo texto.

- Cabeceras, pies y números de página: una línea al principio o al final de la página que se repite (con los números
  cambiados por «#») en la mitad de las páginas o más, y en 3 como mínimo, o que solo es un número de página («3»,
  «- 3 -», «Página 3 de 10», «3/10»).
- Párrafos: una línea en blanco, una viñeta, una línea corta que acaba en punto o un título (una línea corta suelta
  antes de otra que empieza en mayúscula) cierran el párrafo; las palabras partidas con guion al final de la línea se
  vuelven a unir. Un párrafo que no acaba en punto sigue en la página siguiente.
- Frases y trozos: las frases se cortan en «.», «!», «?» y «…» seguidos de mayúscula o cifra, sin cortar en
  abreviaturas («Sr.», «p. ej.», «Mr.») ni en iniciales; dentro de cada frase, los trozos se cortan en «,», «;», «:» y
  rayas, y nunca pasan de `MAX_WORDS` palabras, para que espeak-ng no los parta por su cuenta.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

EDGE_LINES = 2  # líneas del principio y del final de cada página que pueden ser cabecera o pie
MAX_FURNITURE = 150  # una cabecera o un pie es una línea corta
MAX_WORDS = 40  # palabras por trozo como mucho (espeak-ng parte las cláusulas de unas 80)
MAX_CHARS = 260
TERMINAL = (".", "!", "?", "…", ":", "»", "”", '"', ")")
BULLET = re.compile(r"^\s*(?:[•·▪●◦■□►‣⁃*]|[-–—](?=\s))\s*")
PAGE_NUMBER = re.compile(
    r"^\s*(?:(?:p[áa]g(?:ina)?|page|p)\.?\s*)?[-–—(\[]?\s*\d{1,4}\s*[-–—)\]]?\s*(?:(?:/|de|of)\s*\d{1,4})?\s*$", re.I)
# Marcas de guion de fin de línea que dejan algunos PDF: guion blando, el \x02 de PDFium y U+FFFE.
SOFT_HYPHENS = ("­", "\x02", "￾")
ABBREVIATIONS = {
    "sr", "sra", "srta", "sres", "dr", "dra", "dña", "d", "ud", "uds", "vd", "vds", "etc", "pág", "págs", "p", "pp", "ej",
    "núm", "nº", "art", "arts", "cap", "fig", "figs", "vol", "aprox", "tel", "telf", "av", "avda", "c", "ctra", "dto",
    "mr", "mrs", "ms", "prof", "st", "vs", "no", "inc", "ltd", "co", "jr", "sr", "approx", "dept", "est", "e.g", "i.e",
    "p.ej", "ee.uu", "ss", "ibid", "op", "cit",
}
SENTENCE_END = re.compile(r"[.!?…]+[\"”»’')\]]*\s+(?=[\"“«¿¡(\[]?[A-ZÁÉÍÓÚÑÜ0-9])")
CLAUSE_BREAK = re.compile(r"([,;:])\s+|\s+([—–])\s+")
# Lo que queda dentro de un trozo y espeak-ng tomaría como final de cláusula (o no sabe leer) se cambia por un espacio.
STRAY = re.compile(r"[;:!?¡¿()\[\]{}«»\"“”„…—–•·▪●◦■□►‣⁃*_#|<>~^=\\]")
STRAY_DOT = re.compile(r"(?<!\d)[.,]|[.,](?!\d)")  # puntos y comas que no van entre dos cifras («3,5» y «1.000» se quedan)
WORD = re.compile(r"[a-záéíóúüñ]+")

# Palabras muy frecuentes de cada idioma que casi nunca aparecen en el otro (para «Detectar el idioma»).
ES_WORDS = set("""de la que el en y los del se las por un para con una su al lo como más pero sus le ya este porque esta
entre cuando muy sin sobre también hasta hay donde quien desde todo nos durante todos uno les ni contra otros ese eso
ante ellos esto antes algunos qué unos yo otro otras otra él tanto esa estos mucho quienes nada muchos cual poco ella
estar estas algunas algo nosotros es son está fue ha han ser sido tiene puede están hace así según cada años""".split())
EN_WORDS = set("""the of and to in is that for it as with was on be by this are at from or an have not which but you they
his her has had were been their we will would there can all its if more when who what so about one than into them only
other also some could these may then do any should our such through after over between those because how where
""".split())


@dataclass
class Clause:
    text: str  # lo que lee espeak-ng, sin puntuación
    mark: str  # puntuación que va detrás en la entrada de Kokoro («,», «.», «?»…) o «» si el trozo se partió por largo


def page_text(textpage) -> str:
    """Texto de una página de pypdfium2 con una línea en blanco donde hay más espacio de lo normal entre dos líneas
    (un cambio de párrafo, que PDFium no marca). La posición de cada línea es la de su primer carácter."""
    text = textpage.get_text_range().replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    bottoms: list[float | None] = []
    offset = 0
    for line in lines:
        bottom = None
        if line.strip():
            try:
                left, bottom, right, top = textpage.get_charbox(offset + len(line) - len(line.lstrip()), loose=True)
                bottom = bottom if top > bottom else None
            except Exception:  # noqa: BLE001 - sin posición, la línea no cuenta para los saltos
                bottom = None
        bottoms.append(bottom)
        offset += len(line) + 2  # PDFium cuenta el «\r\n» que genera entre líneas
    gaps = [a - b for a, b in zip(bottoms, bottoms[1:]) if a is not None and b is not None and a > b]
    if len(gaps) < 2:
        return text
    usual = sorted(gaps)[len(gaps) // 4]  # el interlineado normal (con pocas líneas, la mediana ya sería un salto)
    out = [lines[0]]
    for i in range(1, len(lines)):
        a, b = bottoms[i - 1], bottoms[i]
        if a is not None and b is not None and a - b > 1.6 * usual and out[-1].strip():
            out.append("")
        out.append(lines[i])
    return "\n".join(out)


def _norm(line: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.strip().lower()))


def _lines(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def strip_furniture(pages: list[str], reference: list[str] | None = None) -> list[list[str]]:
    """Líneas de cada página sin cabeceras, pies ni números de página. `reference` son todas las páginas del documento,
    para reconocer las cabeceras aunque solo se lea un rango."""
    split = [_lines(p) for p in pages]
    sample = [_lines(p) for p in reference] if reference else split
    n = len(sample)
    counts: Counter[str] = Counter()
    for lines in sample:
        content = [ln for ln in lines if ln.strip()]
        counts.update({_norm(ln) for ln in content[:EDGE_LINES] + content[-EDGE_LINES:]})
    # Con menos de 3 páginas no se puede distinguir una cabecera de un texto que se repite: solo números de página.
    need = max(3, (n + 1) // 2)
    repeated = {k for k, c in counts.items() if c >= need and k.strip("# ") and len(k) <= MAX_FURNITURE}

    def furniture(line: str) -> bool:
        return bool(PAGE_NUMBER.match(line)) or _norm(line) in repeated

    out = []
    for lines in split:
        lines = list(lines)
        for _ in range(EDGE_LINES):
            while lines and not lines[0].strip():
                lines.pop(0)
            if lines and furniture(lines[0]):
                lines.pop(0)
        for _ in range(EDGE_LINES):
            while lines and not lines[-1].strip():
                lines.pop()
            if lines and furniture(lines[-1]):
                lines.pop()
        out.append(lines)
    return out


def _clean_line(line: str) -> str:
    line = unicodedata.normalize("NFC", line)
    line = "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") and c not in SOFT_HYPHENS else c for c in line)
    return re.sub(r"[ \t  -​  　]+", " ", line).strip()


def _join(prev: str, line: str) -> str:
    """Une dos líneas de un párrafo; «infor-» + «mación» da «información»."""
    for mark in SOFT_HYPHENS:
        if prev.endswith(mark):
            return prev[: -len(mark)] + line
    if re.search(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]-$", prev) and line[:1].islower():
        return prev[:-1] + line
    return f"{prev} {line}"


def paragraphs(pages: list[str], skip_furniture: bool = True, reference: list[str] | None = None) -> list[str]:
    """Párrafos que se leen, en orden, a partir del texto de cada página (`reference`: todas las del documento)."""
    split = strip_furniture(pages, reference) if skip_furniture else [_lines(p) for p in pages]
    out: list[str] = []
    current = ""
    last_len = 0

    def flush() -> None:
        nonlocal current
        text = current
        for mark in SOFT_HYPHENS:
            text = text.replace(mark, "")
        text = re.sub(r"\s+", " ", text).strip()
        if re.search(r"[^\W_]", text):
            out.append(text)
        current = ""

    joined = 0
    for lines in split:
        widths = sorted(len(_clean_line(ln)) for ln in lines if ln.strip())
        # Ancho de una línea llena de esta página (con pocas líneas, la más larga).
        typical = (widths[-1] if len(widths) < 10 else widths[int(0.9 * (len(widths) - 1))]) if widths else 0
        for raw in lines:
            line = _clean_line(raw)
            if not line:
                flush()
                continue
            bullet = BULLET.match(line)
            starts = line[:1].isupper() or line[:1].isdigit()
            if bullet:
                flush()
                line = line[bullet.end():]
                if not line:
                    continue
            elif current and current.endswith(TERMINAL) and last_len < 0.8 * typical:
                flush()
            elif current and joined == 1 and starts and not current.endswith((",", ";", "-")) and last_len < 0.6 * typical:
                flush()  # un título: una línea corta suelta antes de un párrafo
            if current:
                current = _join(current, line)
                joined += 1
            else:
                current, joined = line, 1
            last_len = len(line)
        if current and current.endswith(TERMINAL):
            flush()
    flush()
    return out


def chars(paras: list[str]) -> int:
    """Caracteres que se leen (el límite `tts_chars_task` de 9.3): los de los párrafos, con sus espacios."""
    return sum(len(p) for p in paras)


def detect_language(text: str, fallback: str | None = None) -> str | None:
    """«es» o «en» según las palabras más frecuentes (en un texto normal son la tercera parte o más). Con muy poco texto
    para saberlo (menos de 20 palabras), `fallback`; si no parece ninguno de los dos, None."""
    words = WORD.findall(text[:60_000].lower())
    es = sum(1 for w in words if w in ES_WORDS) + sum(2 for c in text[:60_000] if c in "ñÑ¿¡")
    en = sum(1 for w in words if w in EN_WORDS)
    if es + en >= max(3, 0.15 * len(words)):
        return "es" if es >= en else "en"
    return fallback if len(words) < 20 else None


def _abbreviation(before: str) -> bool:
    word = re.split(r"[\s(\[\"“«]", before)[-1].lower()
    return word in ABBREVIATIONS or (len(word) == 1 and word.isalpha())


def sentences(paragraph: str) -> list[str]:
    out: list[str] = []
    start = 0
    for m in SENTENCE_END.finditer(paragraph):
        term = re.match(r"[.!?…]+", m.group(0)).group(0)
        if term == "." and _abbreviation(paragraph[start:m.start()]):
            continue
        out.append(paragraph[start:m.end()].strip())
        start = m.end()
    tail = paragraph[start:].strip()
    if tail:
        out.append(tail)
    return out


def _speakable(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'")
    text = STRAY.sub(" ", text)
    text = STRAY_DOT.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _end_mark(sentence: str) -> str:
    tail = re.sub(r"[\"”»’')\]\s]+$", "", sentence)[-3:]
    if "?" in tail:
        return "?"
    if "!" in tail:
        return "!"
    if tail.endswith("…") or tail.endswith("..."):
        return "…"
    return "."


def _split_long(text: str) -> list[str]:
    words = text.split()
    parts: list[list[str]] = [[]]
    for w in words:
        if parts[-1] and (len(parts[-1]) >= MAX_WORDS or len(" ".join(parts[-1])) + 1 + len(w) > MAX_CHARS):
            parts.append([])
        parts[-1].append(w[:MAX_CHARS])
    return [" ".join(p) for p in parts if p]


def clauses(sentence: str) -> list[Clause]:
    """Trozos de una frase con la puntuación que los sigue; los que no tienen nada que leer se descartan."""
    out: list[Clause] = []
    start = 0
    pieces: list[tuple[str, str]] = []
    for m in CLAUSE_BREAK.finditer(sentence):
        pieces.append((sentence[start:m.start()], m.group(1) or "—"))
        start = m.end()
    pieces.append((sentence[start:], _end_mark(sentence)))
    for text, mark in pieces:
        spoken = _speakable(text)
        if not re.search(r"[^\W_]", spoken):
            if out and mark in ".?!…":
                out[-1].mark = mark
            continue
        parts = _split_long(spoken)
        for i, part in enumerate(parts):
            out.append(Clause(part, mark if i == len(parts) - 1 else ""))
    return out
