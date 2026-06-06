"""Localiza cada pasaje dentro del PDF: página + rectángulos para resaltar.

Best-effort y DESACOPLADO del parser: alinea el texto limpio de cada pasaje
contra el flujo de caracteres del PDF (filtrando encabezados/pies, igual que
`_strip_headers`) y devuelve la página física (1-based, para `#page=N`) y los
rectángulos de resaltado. Si un pasaje no se puede alinear, se omite (la UI cae
a 'sin resaltado'). Coordenadas en puntos PDF, origen ARRIBA-IZQUIERDA
(convención de pdfplumber: x0/x1, top/bottom) — cómodo para un overlay HTML.
"""
from __future__ import annotations

import re
import unicodedata

import pdfplumber

from .parse import HEADER_PREFIXES, PAGE_FOOTER_RE

_KEEP = re.compile(r"[a-z0-9]")


def _norm_char(ch: str) -> str:
    """Normaliza un carácter a [a-z0-9] o '' (espacios/puntuación/acentos)."""
    d = unicodedata.normalize("NFD", ch.lower())
    base = "".join(c for c in d if unicodedata.category(c) != "Mn")
    return base if _KEEP.fullmatch(base or "") else ""


def _char_stream(pdf: pdfplumber.PDF) -> tuple[list[dict], str]:
    """Flujo de caracteres relevantes (con página y bbox) + cadena normalizada.

    Índice i en la cadena normalizada ↔ chars[i]. Filtra líneas de encabezado y
    pie, replicando `_strip_headers` a nivel de palabra.
    """
    chars: list[dict] = []
    for page in pdf.pages:
        for line in page.extract_text_lines():
            t = line["text"].strip()
            if t.startswith(HEADER_PREFIXES) or PAGE_FOOTER_RE.match(t):
                continue
            for c in line["chars"]:
                n = _norm_char(c["text"])
                if not n:
                    continue
                chars.append({
                    "page": page.page_number,
                    "x0": c["x0"], "x1": c["x1"],
                    "top": c["top"], "bottom": c["bottom"],
                    "n": n,
                })
    return chars, "".join(c["n"] for c in chars)


def _norm_text(s: str) -> str:
    return "".join(_norm_char(c) for c in s)


def _rects(span: list[dict]) -> list[dict]:
    """Agrupa los caracteres del span por (página, línea) en rectángulos."""
    rects: list[dict] = []
    cur: dict | None = None
    for c in span:
        key = (c["page"], round(c["top"]))
        if cur and cur["_key"] == key:
            cur["x0"] = min(cur["x0"], c["x0"]); cur["x1"] = max(cur["x1"], c["x1"])
            cur["top"] = min(cur["top"], c["top"]); cur["bottom"] = max(cur["bottom"], c["bottom"])
        else:
            if cur:
                rects.append(cur)
            cur = {"_key": key, "page": c["page"], "x0": c["x0"], "x1": c["x1"],
                   "top": c["top"], "bottom": c["bottom"]}
    if cur:
        rects.append(cur)
    return [{k: (r[k] if k == "page" else round(r[k], 2))
             for k in ("page", "x0", "top", "x1", "bottom")} for r in rects]


class Locator:
    """Alinea pasajes contra el PDF. Búsqueda monótona (los pasajes vienen en
    orden de documento), con respaldo a búsqueda global."""

    def __init__(self, pdf_path: str):
        with pdfplumber.open(pdf_path) as pdf:
            self.chars, self.norm = _char_stream(pdf)
            self.page_w = round(pdf.pages[0].width, 2)
            self.page_h = round(pdf.pages[0].height, 2)
        self._cursor = 0

    def locate(self, texto: str) -> dict | None:
        nt = _norm_text(texto)
        if len(nt) < 8:
            return None
        idx = self.norm.find(nt, self._cursor)
        if idx == -1:
            idx = self.norm.find(nt)  # respaldo global
        end = idx + len(nt)
        if idx == -1:
            # respaldo: prefijo distintivo (el bloque puede diferir por de-guionado)
            pref = nt[:80]
            idx = self.norm.find(pref, self._cursor)
            if idx == -1:
                idx = self.norm.find(pref)
            if idx == -1:
                return None
            end = idx + len(pref)
        self._cursor = end
        span = self.chars[idx:end]
        return {
            "pagina": span[0]["page"],
            "page_w": self.page_w,
            "page_h": self.page_h,
            "rects": _rects(span),
        }


def annotate(passages: list[dict], pdf_path: str) -> list[dict]:
    """Agrega `coordenadas` (best-effort) a cada pasaje. Mutar in-place."""
    loc = Locator(pdf_path)
    for p in passages:
        p["coordenadas"] = loc.locate(p["texto"])
    return passages
