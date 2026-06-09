"""Materializa los artículos en el repo de datos, en DOS capas independientes.

Arquitectura (ver README): el texto es la fuente de verdad y git es el detector
de cambios. La metadata derivada (fechas de reforma, título, capítulo) es
best-effort y vive aparte, para que mejorarla nunca ensucie el historial del
texto.

  Capa 1 — TEXTO        articulos/NNN.md   solo encabezado + cuerpo fiel
  Capa 3 — METADATA     metadata/*.json    índice derivado, regenerable

`write_articles` y `write_metadata` son independientes: se puede regenerar el
índice sin tocar un solo .md.
"""
from __future__ import annotations

import json
from pathlib import Path

from .normalize import normalize_body
from .parse import Article, parse, version_date
from .passages import all_passages
from .perfil import CPEUM, PerfilFuente
from .segments import segment

FUENTE = CPEUM.fuente   # conservado por compatibilidad; ahora vive en el perfil


def render_markdown(art: Article, *, perfil: PerfilFuente = CPEUM) -> str:
    """Texto del artículo: encabezado + cuerpo en párrafos. Sin metadata.

    Cualquier cambio aquí proviene de un cambio en la ley; git lo detecta.
    """
    body = normalize_body(art.body, art.label, perfil=perfil)
    return f"# {art.label}\n\n{body}\n"


def write_articles(arts: list[Article], data_repo: str, *,
                   perfil: PerfilFuente = CPEUM) -> None:
    """Capa 1: escribe solo los archivos de texto `articulos/NNN.md`."""
    art_dir = Path(data_repo) / "articulos"
    art_dir.mkdir(parents=True, exist_ok=True)
    # Limpiar previos para que las supresiones se reflejen en git.
    for old in art_dir.glob("*.md"):
        old.unlink()
    for art in arts:
        (art_dir / f"{art.key}.md").write_text(
            render_markdown(art, perfil=perfil), encoding="utf-8")


def write_metadata(
    arts: list[Article], data_repo: str, version: str | None = None,
    pdf_path: str | None = None, *, perfil: PerfilFuente = CPEUM
) -> None:
    """Capa 3: escribe el índice derivado en `metadata/` (no toca los .md)."""
    meta_dir = Path(data_repo) / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)

    index = [
        {
            "clave": art.key,
            "articulo": art.number,
            "sufijo": art.suffix,
            "etiqueta": art.label,
            "titulo": art.titulo,
            "capitulo": art.capitulo,
            "ultima_reforma": art.last_reform.isoformat() if art.last_reform else None,
            "num_reformas": len(art.reform_dates),
            "reformas": [d.isoformat() for d in art.reform_dates],
            "archivo": f"articulos/{art.key}.md",
        }
        for art in arts
    ]
    index_doc = {"fuente": perfil.fuente, "version": version, "articulos": index}
    (meta_dir / "articulos.json").write_text(
        json.dumps(index_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Mapa reforma → artículos afectados, ordenado por fecha.
    reformas: dict[str, list[str]] = {}
    for art in arts:
        for d in art.reform_dates:
            reformas.setdefault(d.isoformat(), []).append(art.key)
    reformas_sorted = {k: sorted(set(v)) for k, v in sorted(reformas.items())}
    (meta_dir / "reformas.json").write_text(
        json.dumps(reformas_sorted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Descomposición en bloques con la reforma de cada uno ya enlazada (para LLM).
    seg_dir = meta_dir / "segmentos"
    seg_dir.mkdir(parents=True, exist_ok=True)
    for old in seg_dir.glob("*.json"):
        old.unlink()
    for art in arts:
        (seg_dir / f"{art.key}.json").write_text(
            json.dumps(segment(art, perfil=perfil), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )

    # Índice plano de pasajes, listo para ingesta de un RAG (un JSON por línea).
    pasajes = all_passages(arts, version, perfil=perfil)
    # Coordenadas en el PDF (página + rects de resaltado), best-effort.
    if pdf_path:
        from .locate import annotate
        annotate(pasajes, pdf_path)
    with (meta_dir / "pasajes.jsonl").open("w", encoding="utf-8") as fh:
        for p in pasajes:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")


def build(pdf_path: str, data_repo: str, what: str = "all", *,
          perfil: PerfilFuente = CPEUM, version: str | None = None) -> list[Article]:
    """Parsea el PDF y materializa las capas pedidas. Devuelve los artículos.

    what: "all" (texto + metadata) | "text" (solo capa 1) | "metadata" (solo capa 3).
    version: override explícito (YYYY-MM-DD) cuando el PDF no trae la fecha en su
    portada (p.ej. Jalisco, cuya versión va en el nombre del archivo).
    """
    arts = parse(pdf_path, perfil=perfil)
    if what in ("all", "text"):
        write_articles(arts, data_repo, perfil=perfil)
    if what in ("all", "metadata"):
        if version is None:
            v = version_date(pdf_path, perfil=perfil)
            version = v.isoformat() if v else None
        write_metadata(arts, data_repo, version=version,
                       pdf_path=pdf_path, perfil=perfil)
    return arts
