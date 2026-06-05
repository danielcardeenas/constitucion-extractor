"""Normaliza el cuerpo crudo de un artículo a párrafos limpios.

El PDF entrega saltos de línea "visuales" (cada ~95 caracteres), no de
párrafo. Para que un `git diff` de una reforma muestre solo el párrafo
cambiado, re-unimos esos saltos suaves y separamos en bloques lógicos:

- Marcadores estructurales (fracciones romanas, incisos, apartados).
- Notas de reforma al pie ("... DOF DD-MM-YYYY").
"""
from __future__ import annotations

import re

# Inicio de una nota de reforma al pie. Las notas describen el cambio y citan
# una o más fechas DOF. Pueden ser compuestas ("... DOF 06-06-2019. Reformada y
# recorrida (antes fracción VII) DOF 30-09-2024") y a veces tan largas que el
# PDF las envuelve en varias líneas (ver _note_is_complete).
REFORM_NOTE_START_RE = re.compile(
    r"^(?:Párrafo|Fracción|Inciso|Apartado|Artículo|Reforma|Adicion|Derogad|"
    r"Reformad|Recorrid|Denominación|Fe de|Adicionad)\b.*DOF\s+\d{2}-\d{2}-\d{4}",
)
REFORM_NOTE_RE = REFORM_NOTE_START_RE  # alias retrocompatible

# Una nota está "completa" cuando termina en una fecha DOF (con posible "."/")"
# final). Si no, la(s) línea(s) siguiente(s) son su continuación envuelta. Como
# toda nota cierra siempre en una fecha, basta seguir uniendo líneas hasta que
# la nota cierre en fecha (sin importar con qué palabra empiece la continuación).
NOTE_COMPLETE_RE = re.compile(r"\d{2}-\d{2}-\d{4}[.)]?$")
# Tope de seguridad: las notas envueltas reales ocupan 1–2 renglones extra.
MAX_NOTE_CONT_LINES = 4

# Marcadores de inicio de fracción / inciso / apartado:
#   "I.", "XiV.", "a)", "1.", "A. " (apartado), "Bis"
STRUCT_MARKER_RE = re.compile(
    r"^(?:[IVXLCDM]+\.|[a-z]\)|\d+\.|[A-Z]\.\s)",
)

# Fin de oración / bloque: el renglón anterior cierra con punto o dos puntos.
SENTENCE_END_RE = re.compile(r"[.:;]$")


def _is_reform_note(line: str) -> bool:
    return bool(REFORM_NOTE_START_RE.match(line.strip()))


def _is_struct_marker(line: str) -> bool:
    return bool(STRUCT_MARKER_RE.match(line.strip()))


def _note_is_complete(note: str) -> bool:
    return bool(NOTE_COMPLETE_RE.search(note.strip()))


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

    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            flush_buf()
            i += 1
            continue
        if _is_reform_note(s):
            flush_buf()
            # Reensamblar notas envueltas: seguir uniendo líneas mientras la nota
            # no cierre en una fecha y la siguiente línea sea su continuación.
            note = s
            j = i + 1
            while (
                j < n
                and (j - i) <= MAX_NOTE_CONT_LINES
                and not _note_is_complete(note)
                and lines[j].strip()
                and not _is_struct_marker(lines[j])
                and not _is_reform_note(lines[j])
            ):
                note = f"{note} {lines[j].strip()}"
                j += 1
            blocks.append(f"_{note}_")        # anotación de reforma en cursiva
            i = j
            continue
        if _is_struct_marker(s):
            flush_buf()
            buf.append(s)
            i += 1
            continue
        # Continuación de párrafo, salvo que el bloque previo ya haya cerrado
        # oración (heurística para no pegar párrafos distintos).
        if buf and SENTENCE_END_RE.search(buf[-1]):
            flush_buf()
        buf.append(s)
        i += 1

    flush_buf()
    return "\n\n".join(b for b in blocks if b).strip()
