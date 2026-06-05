"""Capa 3 — descompone cada artículo en bloques con su reforma ya enlazada.

Objetivo: que un LLM no tenga que inferir a qué párrafo/fracción corresponde
cada nota de reforma. La asociación se vuelve dato explícito.

Convención del DOF (verificada en el documento): una nota refiere al bloque
inmediatamente anterior, y su primera palabra define el alcance
(Párrafo / Fracción / Inciso / Apartado / Artículo). Aquí:

- Cada bloque de texto queda con su `reforma` enlazada (o None si es original).
- El enlace usa el ALCANCE de la nota: una nota "Fracción ..." se ancla a la
  fracción más cercana hacia arriba, aunque en medio haya sub-párrafos.
- Las notas de alcance "Artículo" no se cuelgan de ningún párrafo: van a
  `reformas_articulo`, a nivel raíz.

Es derivado y best-effort: si el enlace falla, el texto del .md sigue intacto.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .normalize import normalize_body
from .parse import Article, reform_dates_in

# Clasificación del marcador que abre un bloque.
RE_FRACCION = re.compile(r"^([IVXLCDM]+)\.")     # I.  II.  XIV.
RE_INCISO = re.compile(r"^([a-z])\)")            # a)  b)
RE_APARTADO = re.compile(r"^([A-Z])\.\s")        # A.  B.   (apartado con punto)
RE_APARTADO_PAREN = re.compile(r"^([A-Z])\)")    # A)  B)   (apartado con paréntesis: art. 30, 37)
RE_NUMERAL = re.compile(r"^(\d+)\.")             # 1.  2.

# Una marca de UNA sola letra romana es ambigua: como fracción solo tienen
# sentido I, V, X (1, 5, 10); C/D/L/M serían fracciones 100+ (imposibles), así
# que esas letras sueltas son en realidad apartados (Apartado C, Apartado D...).
FRACCION_SINGLE = {"I", "V", "X"}


@dataclass
class Reforma:
    nota: str
    fechas: list[str]


@dataclass
class Bloque:
    id: str
    tipo: str                       # parrafo | fraccion | inciso | apartado | numeral
    marca: str                      # "", "I", "a", "A", "1"
    apartado: str                   # contexto de apartado ("A"), "" si no aplica
    fraccion: str                   # contexto de fracción padre ("IV") para incisos/numerales
    ruta: str                       # migaja: "Artículo 2o. › Apartado A › Fracción I"
    texto: str
    reformas: list[Reforma] = field(default_factory=list)


def _classify(text: str) -> tuple[str, str]:
    """(tipo, marca) del bloque a partir de su inicio."""
    if (m := RE_FRACCION.match(text)):
        roman = m.group(1)
        if len(roman) > 1 or roman in FRACCION_SINGLE:
            return "fraccion", roman
        return "apartado", roman             # C/D/L/M sueltas = apartado
    if (m := RE_INCISO.match(text)):
        return "inciso", m.group(1)
    if (m := RE_APARTADO.match(text)) or (m := RE_APARTADO_PAREN.match(text)):
        return "apartado", m.group(1)
    if (m := RE_NUMERAL.match(text)):
        return "numeral", m.group(1)
    return "parrafo", ""


def _note_scope(note: str) -> str:
    """Alcance de una nota a partir de su texto: el primer sustantivo que cita."""
    s = note.strip("_ ").strip()
    if re.match(r"^Artículo\b", s):
        return "articulo"
    low = s.lower()
    # Prioridad por especificidad; el sustantivo guía qué unidad modifica.
    positions = {
        "fraccion": low.find("fracción"),
        "inciso": low.find("inciso"),
        "apartado": low.find("apartado"),
        "parrafo": low.find("párrafo"),
    }
    found = {k: v for k, v in positions.items() if v >= 0}
    if found:
        return min(found, key=found.get)     # el que aparece primero en la nota
    return "parrafo"                          # respaldo posicional


def _is_note(chunk: str) -> bool:
    return chunk.startswith("_") and chunk.endswith("_")


def segment(art: Article) -> dict:
    """Descompone un artículo en bloques con su reforma enlazada."""
    chunks = [c for c in normalize_body(art.body, art.label).split("\n\n") if c.strip()]

    bloques: list[Bloque] = []
    reformas_articulo: list[Reforma] = []
    cur_apartado = ""   # contexto "A"/"B"... mientras estemos dentro de un apartado
    cur_fraccion = ""   # fracción padre actual (para anidar incisos/numerales)
    p_idx = 0           # contador de párrafos para ids estables

    for chunk in chunks:
        if _is_note(chunk):
            nota = chunk.strip("_")
            ref = Reforma(nota=nota, fechas=[d.isoformat() for d in reform_dates_in(nota)])
            scope = _note_scope(nota)
            if scope == "articulo":
                reformas_articulo.append(ref)
                continue
            # Anclar a la unidad del alcance más cercana hacia arriba. Un bloque
            # puede acumular varias notas (p. ej. reforma + fe de erratas).
            target = next(
                (b for b in reversed(bloques) if b.tipo == scope),
                bloques[-1] if bloques else None,
            )
            if target is not None:
                target.reformas.append(ref)
            continue

        tipo, marca = _classify(chunk)

        # Sub-párrafo de una fracción/inciso abierto → se une a ese bloque (su
        # nota de "Fracción/Inciso" debe cubrir todo, no solo el sub-párrafo).
        if tipo == "parrafo" and bloques and bloques[-1].tipo in ("fraccion", "inciso") \
                and not bloques[-1].reformas:
            bloques[-1].texto += "\n\n" + chunk
            continue

        # Actualizar el contexto jerárquico.
        if tipo == "apartado":
            cur_apartado, cur_fraccion = marca, ""
        elif tipo == "fraccion":
            cur_fraccion = marca

        ap = f"{cur_apartado}." if cur_apartado and tipo != "apartado" else ""
        fr = f"{cur_fraccion}." if cur_fraccion and tipo in ("inciso", "numeral") else ""
        if tipo == "parrafo":
            p_idx += 1
            bid = f"{art.key}.p{p_idx}"
        else:
            bid = f"{art.key}.{ap}{fr}{marca}"

        ruta = art.label
        if cur_apartado and tipo != "apartado":
            ruta += f" › Apartado {cur_apartado}"
        if cur_fraccion and tipo in ("inciso", "numeral"):
            ruta += f" › Fracción {cur_fraccion}"
        ruta += {
            "parrafo": f" › párrafo {p_idx}",
            "fraccion": f" › Fracción {marca}",
            "inciso": f" › inciso {marca})",
            "apartado": f" › Apartado {marca}",
            "numeral": f" › {marca}.",
        }[tipo]

        bloques.append(Bloque(id=bid, tipo=tipo, marca=marca,
                              apartado=cur_apartado if tipo != "apartado" else "",
                              fraccion=cur_fraccion if tipo in ("inciso", "numeral") else "",
                              ruta=ruta, texto=chunk))

    # Garantía de unicidad: en artículos con anidamiento profundo (p. ej. 41,
    # 123, donde hay apartados dentro de fracciones) el id semántico puede
    # repetirse. Lo desambiguamos con un sufijo para que cada bloque sea
    # direccionable de forma única. El `ruta`/`marca` siguen dando la ubicación.
    seen: dict[str, int] = {}
    for b in bloques:
        if b.id in seen:
            seen[b.id] += 1
            b.id = f"{b.id}~{seen[b.id]}"
        else:
            seen[b.id] = 1

    def _clean(b: Bloque) -> dict:
        d = asdict(b)
        if not d["reformas"]:
            d.pop("reformas")
        return d

    return {
        "clave": art.key,
        "etiqueta": art.label,
        "titulo": art.titulo,
        "capitulo": art.capitulo,
        "reformas_articulo": [asdict(r) for r in reformas_articulo],
        "bloques": [_clean(b) for b in bloques],
    }
