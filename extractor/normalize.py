"""Normaliza el cuerpo crudo de un artículo a párrafos limpios.

El PDF entrega saltos de línea "visuales" (cada ~95 caracteres), no de
párrafo. Para que un `git diff` de una reforma muestre solo el párrafo
cambiado, re-unimos esos saltos suaves y separamos en bloques lógicos:

- Marcadores estructurales (fracciones romanas, incisos, apartados).
- Notas de reforma al pie ("... DOF DD-MM-YYYY").
"""
from __future__ import annotations

import re

# Nota de reforma al pie: línea que describe la reforma y termina en fechas DOF.
REFORM_NOTE_RE = re.compile(
    r"^(?:Párrafo|Fracción|Inciso|Apartado|Artículo|Reforma|Adicion|Derogad|"
    r"Reformad|Recorrid|Fe de|Adicionad)\b.*DOF\s+\d{2}-\d{2}-\d{4}",
)

# Marcadores de inicio de fracción / inciso / apartado:
#   "I.", "XiV.", "a)", "1.", "A. " (apartado), "Bis"
STRUCT_MARKER_RE = re.compile(
    r"^(?:[IVXLCDM]+\.|[a-z]\)|\d+\.|[A-Z]\.\s)",
)

# Fin de oración / bloque: el renglón anterior cierra con punto o dos puntos.
SENTENCE_END_RE = re.compile(r"[.:;]$")


def _is_reform_note(line: str) -> bool:
    return bool(REFORM_NOTE_RE.match(line.strip()))


def _is_struct_marker(line: str) -> bool:
    return bool(STRUCT_MARKER_RE.match(line.strip()))


def normalize_body(body: str, heading_label: str) -> str:
    """Devuelve el cuerpo del artículo como párrafos, sin la línea de encabezado.

    Las notas de reforma quedan en *cursiva* como anotación al pie de su bloque.
    """
    lines = [ln.rstrip() for ln in body.splitlines()]

    # Quitar la primera línea (el encabezado "Artículo No. ..."): el texto que
    # le sigue en el mismo renglón se conserva.
    if lines:
        first = lines[0]
        # "Artículo 4o.- La mujer..." → "La mujer..."
        m = re.match(r"^Artículo\s+\d+\s*[oº°]?\s*(?:Bis|Ter)?\.?-?\s*", first)
        lines[0] = first[m.end():] if m else first

    blocks: list[str] = []
    buf: list[str] = []

    def flush_buf() -> None:
        if buf:
            blocks.append(" ".join(w.strip() for w in buf if w.strip()))
            buf.clear()

    for line in lines:
        s = line.strip()
        if not s:
            flush_buf()
            continue
        if _is_reform_note(s):
            flush_buf()
            blocks.append(f"_{s}_")          # anotación de reforma en cursiva
            continue
        if _is_struct_marker(s):
            flush_buf()
            buf.append(s)
            continue
        # Continuación de párrafo, salvo que el bloque previo ya haya cerrado
        # oración (heurística para no pegar párrafos distintos).
        if buf and SENTENCE_END_RE.search(buf[-1]):
            flush_buf()
        buf.append(s)

    flush_buf()
    return "\n\n".join(b for b in blocks if b).strip()
