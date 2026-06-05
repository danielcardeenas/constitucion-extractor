"""Segmentación del PDF de la CPEUM en artículos estructurados.

El PDF oficial (Cámara de Diputados) es texto digital, no escaneado.
Cada página repite un encabezado de 4 líneas y el articulado termina
donde empiezan los "Transitorios". Las notas de reforma vienen al pie
de cada artículo/párrafo con el patrón "... DOF DD-MM-YYYY".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import pdfplumber

# Líneas de encabezado que se repiten en cada página y deben eliminarse.
HEADER_PREFIXES = (
    "CONSTITUCIÓN POLÍTICA",
    "CÁMARA DE DIPUTADOS",
    "Secretaría General",
    "Secretaría de Servicios",
)

# Inicio de un artículo: "Artículo 1o.", "Artículo 27.", "Artículo 73.-",
# "Artículo 4o. Bis", "Artículo 26." (solo, en su línea), etc.
# - SIN IGNORECASE a propósito: los encabezados reales siempre llevan "Artículo"
#   con mayúscula; las citas a mitad de oración usan "artículo" minúscula.
# - El separador final admite fin de línea ($) para artículos cuyo encabezado va
#   solo en su renglón (p. ej. el 26, que tiene apartados A/B debajo).
ARTICLE_RE = re.compile(
    r"^Artículo\s+(\d+)\s*[oº°]?\s*(Bis|Ter)?\.?-?(?:\s|$)",
)

# Encabezado de Título: "Título Primero" exacto (evita "título profesional...").
TITULO_RE = re.compile(
    r"^T[íi]tulo\s+(Primero|Segundo|Tercero|Cuarto|Quinto|Sexto|"
    r"Séptimo|Octavo|Noveno|Décimo)\b.*$",
)
# Encabezado de Capítulo: "Capítulo I", "Capítulo II Bis", etc.
CAPITULO_RE = re.compile(r"^Cap[íi]tulo\s+([IVXLC]+)(\s+Bis)?\s*$")

# Frontera del articulado permanente: el primer encabezado de Transitorios,
# que en el PDF oficial es "Artículos Transitorios" (los del texto original de
# 1917) y aparece justo después del Artículo 136. Todo lo que sigue son los
# transitorios de cada reforma y no forma parte del articulado vigente.
TRANSITORIOS_RE = re.compile(
    r"^[ \t]*(?:Artículos?\s+Transitorios?|ARTÍCULOS?\s+TRANSITORIOS?|TRANSITORIOS?)[ \t]*$",
    re.MULTILINE,
)

# Fechas de reforma dentro de las notas al pie. Una cláusula DOF puede encadenar
# varias fechas con coma: "DOF 04-12-2006, 10-06-2011". Capturamos la cláusula
# completa y luego cada fecha, para no perder las encadenadas.
DOF_CLAUSE_RE = re.compile(
    r"DOF\s+(\d{2}-\d{2}-\d{4}(?:\s*,\s*\d{2}-\d{2}-\d{4})*)"
)
DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


def reform_dates_in(text: str) -> list[date]:
    """Todas las fechas de reforma (DOF) presentes en `text`, únicas y ordenadas."""
    dates: set[date] = set()
    for clause in DOF_CLAUSE_RE.findall(text):
        for d, mo, y in DATE_RE.findall(clause):
            dates.add(date(int(y), int(mo), int(d)))
    return sorted(dates)


@dataclass
class Article:
    number: int
    suffix: str = ""           # "", "Bis", "Ter"
    titulo: str = ""           # Título al que pertenece
    capitulo: str = ""         # Capítulo al que pertenece
    body: str = ""             # texto completo del artículo
    reform_dates: list[date] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Identificador estable: '004', '004-bis'."""
        base = f"{self.number:03d}"
        return f"{base}-{self.suffix.lower()}" if self.suffix else base

    @property
    def label(self) -> str:
        # Ordinal oficial: del 1 al 9 se escribe "1o.".."9o."; del 10 en adelante
        # sin ordinal ("10.", "11.", ...). El sufijo Bis/Ter va al final.
        num = f"{self.number}o." if self.number <= 9 else f"{self.number}."
        suf = f" {self.suffix}" if self.suffix else ""
        return f"Artículo {num}{suf}"

    @property
    def last_reform(self) -> date | None:
        return max(self.reform_dates) if self.reform_dates else None


# Pie de página: "1 de 414", "414 de 414" (número de página / total).
PAGE_FOOTER_RE = re.compile(r"^\d{1,3}\s+de\s+414$")


def _strip_headers(page_text: str) -> str:
    lines = []
    for line in page_text.splitlines():
        s = line.strip()
        if s.startswith(HEADER_PREFIXES) or PAGE_FOOTER_RE.match(s):
            continue
        lines.append(line)
    return "\n".join(lines)


# Versión del texto: "Últimas Reformas DOF 02-06-2026" (en la portada del PDF).
VERSION_RE = re.compile(r"[ÚU]ltimas?\s+[Rr]eformas?\s+(?:publicadas\s+)?DOF\s+(\d{2})-(\d{2})-(\d{4})")


def extract_clean_text(pdf_path: str) -> str:
    """Devuelve el texto completo del PDF sin encabezados de página."""
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(_strip_headers(page.extract_text() or ""))
    return "\n".join(parts)


def version_date(pdf_path: str) -> date | None:
    """Fecha de la última reforma incorporada al PDF = versión del snapshot."""
    with pdfplumber.open(pdf_path) as pdf:
        head = pdf.pages[0].extract_text() or ""
    m = VERSION_RE.search(head)
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _articulado_text(text: str) -> str:
    """Recorta el texto al articulado, cortando antes de los Transitorios."""
    m = TRANSITORIOS_RE.search(text)
    return text[: m.start()] if m else text


def parse(pdf_path: str) -> list[Article]:
    """Parsea el PDF y devuelve la lista de artículos en orden."""
    return parse_text(extract_clean_text(pdf_path))


def parse_text(clean_text: str, start: int = 1) -> list[Article]:
    """Segmenta texto ya limpio (sin encabezados) en artículos.

    Separado de `parse` para poder probarlo con texto sintético, sin PDF.
    `start` es el número del primer artículo esperado (1 en el documento real;
    útil en tests para segmentar un artículo suelto, p. ej. el 4o.).
    """
    text = _articulado_text(clean_text)
    lines = text.splitlines()

    articles: list[Article] = []
    current: Article | None = None
    cur_titulo = ""
    cur_capitulo = ""
    expected = start  # número de artículo esperado para validar la secuencia

    def flush(art: Article | None) -> None:
        if art is not None:
            art.body = art.body.strip()
            art.reform_dates = reform_dates_in(art.body)
            articles.append(art)

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        tm = TITULO_RE.match(stripped)
        if tm and current is None or (tm and stripped == tm.group(0)):
            # Solo aceptamos el encabezado de Título fuera del cuerpo de un
            # artículo para evitar capturar "Título Cuarto de esta Constitución".
            if current is None or len(stripped) < 30:
                cur_titulo = stripped
                continue

        cm = CAPITULO_RE.match(stripped)
        if cm and (current is None or len(stripped) < 25):
            cur_capitulo = stripped
            continue

        am = ARTICLE_RE.match(stripped)
        if am:
            num = int(am.group(1))
            suffix = (am.group(2) or "").title()
            # Validar secuencia: solo aceptar el siguiente esperado (o un Bis/Ter
            # del actual). Así descartamos las citas "Artículo 105" en el cuerpo.
            is_next = num == expected
            is_variant = current is not None and num == current.number and suffix
            if is_next or is_variant:
                flush(current)
                current = Article(
                    number=num, suffix=suffix,
                    titulo=cur_titulo, capitulo=cur_capitulo,
                )
                current.body = line + "\n"
                if is_next:
                    expected = num + 1
                continue

        if current is not None:
            current.body += line + "\n"

    flush(current)
    return articles
