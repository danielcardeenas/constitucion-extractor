"""Escribe los artículos parseados como archivos Markdown en el repo de datos.

Diseño orientado a `git diff` limpio:
- Un archivo por artículo: `articulos/004.md`.
- Frontmatter YAML con metadata estable (número, título, capítulo, reformas).
- Cuerpo en párrafos normalizados.
- Un índice `metadata/articulos.json` y un `metadata/reformas.json` agregados.
"""
from __future__ import annotations

import json
from pathlib import Path

from .normalize import normalize_body
from .parse import Article, parse

FUENTE = "Diario Oficial de la Federación — CPEUM, H. Cámara de Diputados"


def _yaml_list(dates) -> str:
    return "[" + ", ".join(d.isoformat() for d in dates) + "]"


def render_markdown(art: Article) -> str:
    body = normalize_body(art.body, art.label)
    fm = [
        "---",
        f"articulo: {art.number}",
        f'clave: "{art.key}"',
        f'titulo: "{art.titulo}"' if art.titulo else 'titulo: ""',
        f'capitulo: "{art.capitulo}"' if art.capitulo else 'capitulo: ""',
        f"ultima_reforma: {art.last_reform.isoformat() if art.last_reform else 'null'}",
        f"reformas: {_yaml_list(art.reform_dates)}",
        f'fuente: "{FUENTE}"',
        "---",
    ]
    return "\n".join(fm) + f"\n\n# {art.label}\n\n{body}\n"


def build(pdf_path: str, data_repo: str) -> list[Article]:
    """Parsea el PDF y materializa los archivos en `data_repo`. Devuelve los artículos."""
    arts = parse(pdf_path)
    root = Path(data_repo)
    art_dir = root / "articulos"
    meta_dir = root / "metadata"
    art_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    # Limpiar artículos previos para que las supresiones se reflejen en git.
    for old in art_dir.glob("*.md"):
        old.unlink()

    index = []
    for art in arts:
        (art_dir / f"{art.key}.md").write_text(render_markdown(art), encoding="utf-8")
        index.append({
            "clave": art.key,
            "articulo": art.number,
            "titulo": art.titulo,
            "capitulo": art.capitulo,
            "ultima_reforma": art.last_reform.isoformat() if art.last_reform else None,
            "num_reformas": len(art.reform_dates),
            "archivo": f"articulos/{art.key}.md",
        })

    (meta_dir / "articulos.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
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
    return arts
