"""Capa de ingesta — aplana los segmentos en 'pasajes' listos para un RAG.

Un pasaje = un bloque citable, con TODO lo que un retriever/LLM necesita para
recuperar, responder y CITAR de forma verificable:

- `id` / `cita` / `ruta`: identificador único + cita legal formal + migaja.
- `texto`: el texto fiel del bloque (lo que se muestra y se cita).
- `texto_embedding`: el texto con su contexto (ruta + título) antepuesto, para
  que la recuperación funcione con preguntas coloquiales.
- Provenance: `fuente`, `url_fuente`, `version` (fecha del PDF).
- Temporal: `vigente_desde` (última reforma del bloque) y `vigente_hasta`
  (null = vigente). En el modelo forward-only, las versiones futuras llenarán
  `vigente_hasta` al regenerar tras una reforma.

Es capa derivada: se regenera; nunca es la fuente de verdad (esa es el .md).
"""
from __future__ import annotations

import re

from .parse import Article
from .perfil import CPEUM, PerfilFuente
from .segments import segment

# Constantes federales conservadas por compatibilidad (ahora viven en el perfil).
FUENTE = CPEUM.fuente
URL_FUENTE = CPEUM.url_fuente
TEXTO_ORIGINAL = CPEUM.texto_original   # fecha del texto original sin reforma

_PARRAFO_ID = re.compile(r"\.p(\d+)")


def _cita(art_label: str, b: dict) -> str:
    """Cita legal formal: 'Artículo 2o., Apartado A, fracción I'."""
    parts = [art_label]
    if b.get("apartado"):
        parts.append(f"Apartado {b['apartado']}")
    if b.get("fraccion"):
        parts.append(f"fracción {b['fraccion']}")
    tipo, marca = b["tipo"], b.get("marca", "")
    if tipo == "fraccion":
        parts.append(f"fracción {marca}")
    elif tipo == "inciso":
        parts.append(f"inciso {marca})")
    elif tipo == "apartado":
        parts.append(f"Apartado {marca}")
    elif tipo == "numeral":
        parts.append(f"numeral {marca}")
    elif tipo == "parrafo":
        m = _PARRAFO_ID.search(b["id"])
        parts.append(f"párrafo {m.group(1)}" if m else "párrafo")
    return ", ".join(parts)


def _bloque_fechas(b: dict) -> list[str]:
    fechas = sorted({f for r in b.get("reformas", []) for f in r["fechas"]})
    return fechas


def passages_for(art: Article, version: str | None, *,
                 perfil: PerfilFuente = CPEUM) -> list[dict]:
    """Pasajes (uno por bloque) de un artículo."""
    doc = segment(art, perfil=perfil)
    out = []
    for b in doc["bloques"]:
        fechas = _bloque_fechas(b)
        vigente_desde = fechas[-1] if fechas else perfil.texto_original
        cita = _cita(doc["etiqueta"], b)
        ctx = f"{b['ruta']} | {doc['titulo']}".strip(" |")
        out.append({
            "id": perfil.prefijo_id(b["id"]),
            "ambito": perfil.ambito,          # partición del corpus (federal/jalisco/…)
            "cita": cita,
            "ruta": b["ruta"],
            "articulo": art.number,
            "clave_articulo": art.key,
            "tipo": b["tipo"],
            "titulo": doc["titulo"],
            "capitulo": doc["capitulo"],
            "texto": b["texto"],
            "texto_embedding": f"{ctx}\n{b['texto']}",
            "reformas": fechas,
            "notas_reforma": [r["nota"] for r in b.get("reformas", [])],
            "vigente_desde": vigente_desde,
            "vigente_hasta": None,            # forward-only: null = vigente
            "version": version,
            "fuente": perfil.fuente,
            "url_fuente": perfil.url_fuente,
            "archivo_texto": f"articulos/{art.key}.md",
        })
    return out


def all_passages(arts: list[Article], version: str | None, *,
                 perfil: PerfilFuente = CPEUM) -> list[dict]:
    return [p for art in arts for p in passages_for(art, version, perfil=perfil)]
