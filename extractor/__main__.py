"""CLI del extractor.

Uso:
    python -m extractor build --pdf CPEUM.pdf --out ../constitucion-mexicana
    python -m extractor stats --pdf CPEUM.pdf
"""
from __future__ import annotations

import argparse
import sys

from .build import build
from .parse import parse


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="extractor", description="Extractor de la CPEUM a Markdown")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Genera el texto (capa 1) y la metadata (capa 3)")
    b.add_argument("--pdf", default="CPEUM.pdf")
    b.add_argument("--out", required=True, help="Ruta al repo de datos (constitucion-mexicana)")
    b.add_argument("--only", choices=["all", "text", "metadata"], default="all",
                   help="Qué capa escribir: all (default), text, metadata")

    idx = sub.add_parser("index", help="Regenera SOLO la metadata derivada (no toca los .md)")
    idx.add_argument("--pdf", default="CPEUM.pdf")
    idx.add_argument("--out", required=True)

    e = sub.add_parser("enriquecer",
                       help="Genera la capa de enriquecimiento por LLM (metadata/generado/)")
    e.add_argument("--pdf", default="CPEUM.pdf")
    e.add_argument("--out", required=True)
    e.add_argument("--proveedor", choices=["anthropic", "openai"], default="openai",
                   help="Proveedor del LLM (default: openai)")
    e.add_argument("--modelo", default=None,
                   help="Modelo a usar (default según proveedor)")
    e.add_argument("--force", action="store_true",
                   help="Regenerar todos, ignorando la caché por hash")

    v = sub.add_parser("validar",
                       help="Verifica invariantes del repo de datos (gate de CI). Sale !=0 si falla")
    v.add_argument("--out", required=True, help="Ruta al repo de datos")
    v.add_argument("--base", default=None,
                   help="Ref git base para checks de diff (p.ej. origin/main)")
    v.add_argument("--max-cambios", type=int, default=20,
                   help="Máximo de artículos que puede tocar una reforma legítima")

    s = sub.add_parser("stats", help="Imprime estadísticas del parseo (no escribe)")
    s.add_argument("--pdf", default="CPEUM.pdf")

    args = p.parse_args(argv)

    if args.cmd == "validar":
        from .validate import format_report, validate
        ok, checks = validate(args.out, base=args.base, max_changes=args.max_cambios)
        print(format_report(checks))
        print("\n" + ("✅ Invariantes OK" if ok else "❌ Invariantes ROTOS — no mergear"))
        return 0 if ok else 1

    if args.cmd == "build":
        arts = build(args.pdf, args.out, what=args.only)
        if args.only == "metadata":
            print(f"✓ metadata de {len(arts)} artículos en {args.out}/metadata/")
        else:
            print(f"✓ {len(arts)} artículos escritos en {args.out}/articulos/")
        return 0

    if args.cmd == "index":
        arts = build(args.pdf, args.out, what="metadata")
        print(f"✓ metadata regenerada para {len(arts)} artículos (sin tocar los .md)")
        return 0

    if args.cmd == "enriquecer":
        from .enrich import DEFAULT_MODELS, caller_for, run_enrichment
        modelo = args.modelo or DEFAULT_MODELS[args.proveedor]
        arts = parse(args.pdf)
        call = caller_for(args.proveedor, modelo)
        stats = run_enrichment(arts, args.out, call, f"{args.proveedor}:{modelo}", force=args.force)
        print(f"✓ enriquecimiento ({args.proveedor}:{modelo}): {stats['generados']} generados, "
              f"{stats['omitidos']} omitidos, {stats['fallidos']} fallidos")
        for err in stats["errores"]:
            print(f"  ⚠ {err}")
        return 0

    if args.cmd == "stats":
        arts = parse(args.pdf)
        nums = [a.number for a in arts]
        gaps = [n for n in range(1, 137) if n not in nums]
        print(f"Artículos: {len(arts)} (rango {min(nums)}–{max(nums)})")
        print(f"Huecos en 1–136: {gaps or 'ninguno'}")
        print(f"Con sufijo: {[a.label for a in arts if a.suffix] or 'ninguno'}")
        total_reformas = sum(len(a.reform_dates) for a in arts)
        print(f"Notas de reforma totales: {total_reformas}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
