"""Segmentación de un PDF legal en artículos estructurados.

El motor es agnóstico a la fuente: toda diferencia entre documentos (CPEUM
federal, constituciones estatales, ...) vive en un `PerfilFuente` (ver
`perfil.py`). El default es `CPEUM`, así que el comportamiento federal previo
se conserva intacto.

Cada PDF entrega texto digital con un encabezado repetido por página; el
articulado termina donde empiezan los "Transitorios". Las notas de reforma
(cuando la fuente las trae inline) van al pie de cada bloque.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pdfplumber

from .perfil import CPEUM, PerfilFuente

# Globales federales conservadas por compatibilidad (apuntan al perfil CPEUM).
ARTICLE_RE = CPEUM.article_re
TITULO_RE = CPEUM.titulo_re
CAPITULO_RE = CPEUM.capitulo_re
TRANSITORIOS_RE = CPEUM.transitorios_re
HEADER_PREFIXES = CPEUM.header_prefixes
PAGE_FOOTER_RE = CPEUM.page_footer_re
VERSION_RE = CPEUM.version_re


def reform_dates_in(text: str) -> list[date]:
    """Fechas de reforma (DOF) en `text`. Federal; ver `PerfilFuente.fechas_de`."""
    return CPEUM.fechas_de(text)


@dataclass
class Article:
    number: int
    suffix: str = ""           # "", "Bis", "Ter"
    titulo: str = ""           # Título al que pertenece
    capitulo: str = ""         # Capítulo al que pertenece
    body: str = ""             # texto completo del artículo
    reform_dates: list[date] = field(default_factory=list)
    label_ordinal: str = "federal"   # estilo del ordinal en la etiqueta

    @property
    def key(self) -> str:
        """Identificador estable: '004', '004-bis'."""
        base = f"{self.number:03d}"
        return f"{base}-{self.suffix.lower()}" if self.suffix else base

    @property
    def label(self) -> str:
        # Ordinal según la fuente: federal "1o."/"10."; "masc" "1º"; "plano" "1".
        if self.label_ordinal == "federal":
            num = f"{self.number}o." if self.number <= 9 else f"{self.number}."
        elif self.label_ordinal == "masc":
            num = f"{self.number}º"
        else:
            num = f"{self.number}"
        suf = f" {self.suffix}" if self.suffix else ""
        return f"Artículo {num}{suf}"

    @property
    def last_reform(self) -> date | None:
        return max(self.reform_dates) if self.reform_dates else None


def _strip_headers(page_text: str, perfil: PerfilFuente) -> str:
    lines = []
    for line in page_text.splitlines():
        s = line.strip()
        if perfil.header_prefixes and s.startswith(perfil.header_prefixes):
            continue
        if perfil.page_footer_re and perfil.page_footer_re.match(s):
            continue
        lines.append(line)
    return "\n".join(lines)


def extract_clean_text(pdf_path: str, *, perfil: PerfilFuente = CPEUM) -> str:
    """Devuelve el texto completo del PDF sin encabezados de página."""
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(_strip_headers(page.extract_text() or "", perfil))
    return "\n".join(parts)


def version_date(pdf_path: str, *, perfil: PerfilFuente = CPEUM) -> date | None:
    """Fecha de la última reforma incorporada al PDF = versión del snapshot."""
    if perfil.version_re is None:
        return None
    with pdfplumber.open(pdf_path) as pdf:
        head = pdf.pages[0].extract_text() or ""
    m = perfil.version_re.search(head)
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _articulado_text(text: str, *, perfil: PerfilFuente = CPEUM) -> str:
    """Recorta el texto al articulado, cortando antes de los Transitorios."""
    m = perfil.transitorios_re.search(text)
    return text[: m.start()] if m else text


def parse(pdf_path: str, *, perfil: PerfilFuente = CPEUM) -> list[Article]:
    """Parsea el PDF y devuelve la lista de artículos en orden."""
    return parse_text(extract_clean_text(pdf_path, perfil=perfil), perfil=perfil)


def parse_text(clean_text: str, start: int = 1, *,
               perfil: PerfilFuente = CPEUM) -> list[Article]:
    """Segmenta texto ya limpio (sin encabezados) en artículos.

    `start` es el número del primer artículo esperado (relevante para el gate
    estricto). El gate del perfil decide cómo se valida la secuencia:
    - "estricto"   (federal): solo el siguiente esperado (rechaza citas inline).
    - "monotonico" (estatal): cualquier número mayor al último (tolera huecos
      por derogación, que en el gate estricto detenían todo el parseo).
    """
    if perfil.preprocess:
        clean_text = perfil.preprocess(clean_text)
    text = _articulado_text(clean_text, perfil=perfil)
    lines = text.splitlines()

    articles: list[Article] = []
    current: Article | None = None
    cur_titulo = ""
    cur_capitulo = ""
    expected = start   # gate estricto: número esperado
    last = start - 1   # gate monotonico: último número aceptado

    def flush(art: Article | None) -> None:
        if art is not None:
            art.body = art.body.strip()
            art.reform_dates = perfil.fechas_de(art.body)
            articles.append(art)

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        tm = perfil.titulo_re.match(stripped)
        if tm and current is None or (tm and stripped == tm.group(0)):
            if current is None or len(stripped) < 30:
                cur_titulo = stripped
                continue

        cm = perfil.capitulo_re.match(stripped)
        if cm and (current is None or len(stripped) < 25):
            cur_capitulo = stripped
            continue

        am = perfil.article_re.match(stripped)
        if am:
            num = int(am.group(1))
            suffix = (am.group(2) or "").title()
            if perfil.gate == "estricto":
                is_accept = num == expected
            else:
                is_accept = num > last
            is_variant = current is not None and num == current.number and bool(suffix)
            if is_accept or is_variant:
                flush(current)
                current = Article(
                    number=num, suffix=suffix,
                    titulo=cur_titulo, capitulo=cur_capitulo,
                    label_ordinal=perfil.label_ordinal,
                )
                current.body = line + "\n"
                if is_accept:
                    expected = num + 1
                    last = num
                continue

        if current is not None:
            current.body += line + "\n"

    flush(current)
    return articles
