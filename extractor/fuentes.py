"""Registro de fuentes conocidas (ámbito → PerfilFuente).

Cada constitución estatal es UN perfil declarativo (Nivel 1). Si un estado
resulta irregular, su perfil sube de nivel: hook (`preprocess`) o, en el
extremo, una `estrategia` con segmentador propio. El gate de `validate.py`
es quien delata cuándo un perfil no basta.
"""
from __future__ import annotations

import re

from .perfil import CPEUM, PerfilFuente, perfil_estatal

JALISCO = perfil_estatal(
    ambito="jalisco",
    clave="jal",
    nombre="Constitución Política del Estado de Jalisco",
    fuente="Periódico Oficial del Estado de Jalisco — Congreso del Estado de Jalisco",
    url_fuente=(
        "https://congresoweb.congresojal.gob.mx/bibliotecavirtual/legislacion/"
        "Constitución/Documentos_PDF-Constitución/"
        "Constitución Política del Estado de Jalisco-180423.pdf"),
    texto_original="1917-08-02",   # vigencia del texto original
    header_prefixes=(),            # no repite encabezado por página
    label_ordinal="masc",          # "Artículo 1º"
)

CDMX = perfil_estatal(
    ambito="cdmx",
    clave="cmx",
    nombre="Constitución Política de la Ciudad de México",
    fuente="Gaceta Oficial de la Ciudad de México — Congreso de la Ciudad de México",
    url_fuente="https://www.congresocdmx.gob.mx/",
    texto_original="2017-02-05",
    header_prefixes=("CONSTITUCIÓN POLÍTICA DE LA CIUDAD",),
    label_ordinal="plano",         # "Artículo 1" (sin ordinal)
    # Excepción Nivel 1: el genérico ^TRANSITORIOS$ no corta en CDMX y el art. 71
    # se traga todo el cierre (transitorios + promulgación + historial de
    # decretos). El articulado termina en el heading "ARTÍCULOS TRANSITORIOS"
    # (transitorios originales de la Constitución). Se admite también la variante
    # "TRANSITORIOS DEL DECRETO POR EL QUE SE EXPIDE..." de otras ediciones.
    transitorios_re=re.compile(
        r"^(?:ART[ÍI]CULOS?\s+TRANSITORIOS\s*$|TR[AÁ]NSITORIOS\s+DEL\s+DECRETO\b)",
        re.MULTILINE),
    # El PDF vigente trae el número de página suelto en su propia línea ("3").
    # Los ítems del articulado llevan punto ("3."), así que solo-dígitos = página.
    page_footer_re=re.compile(r"\d{1,3}$"),
)

# Ámbito → perfil. La clave es lo que se pasa por CLI con --perfil.
FUENTES: dict[str, PerfilFuente] = {
    "cpeum": CPEUM,
    "jalisco": JALISCO,
    "cdmx": CDMX,
}


def perfil_por_nombre(nombre: str) -> PerfilFuente:
    if nombre not in FUENTES:
        disponibles = ", ".join(FUENTES)
        raise SystemExit(f"perfil desconocido: {nombre!r}. Disponibles: {disponibles}")
    return FUENTES[nombre]
