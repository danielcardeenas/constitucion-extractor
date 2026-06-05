#!/usr/bin/env python3
"""Genera el cuerpo (markdown) del PR de actualización de la CPEUM.

Lo usa el Action de vigilancia: tras regenerar el repo de datos, lista los
artículos cuyo texto cambió (vía git) y arma un resumen legible para revisar.

Uso:  python pr_summary.py /ruta/al/repo-de-datos > cuerpo.md
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    ).stdout


def changed_articles(repo: Path) -> list[str]:
    """Claves de artículo con cambios en el árbol de trabajo (modificados/nuevos)."""
    status = _git(repo, "status", "--porcelain", "--", "articulos")
    claves = []
    for line in status.splitlines():
        path = line[3:].strip()
        if "->" in path:                 # renombrado: tomar el destino
            path = path.split("->")[-1].strip()
        if path.endswith(".md"):
            claves.append(Path(path).stem)
    return sorted(set(claves))


def main(repo_arg: str) -> int:
    repo = Path(repo_arg)
    claves = changed_articles(repo)

    idx = json.loads((repo / "metadata" / "articulos.json").read_text(encoding="utf-8"))
    version = idx.get("version")
    by_clave = {a["clave"]: a for a in idx["articulos"]}

    print("## 🏛️ Posible reforma a la CPEUM (detección automática)\n")
    print("El texto vigente del PDF oficial cambió respecto a la versión en este "
          "repositorio. Este PR fue abierto automáticamente para que revises el diff.\n")
    if version:
        print(f"- **Versión del PDF (Últimas reformas DOF):** {version}")
    print(f"- **Artículos con cambios:** {len(claves)}\n")

    if claves:
        print("| Artículo | Última reforma |")
        print("|---|---|")
        for c in claves:
            a = by_clave.get(c, {})
            print(f"| {a.get('etiqueta', c)} | {a.get('ultima_reforma', '—')} |")

    print("\n---\n")
    print("### Antes de aprobar")
    print("- Revisa el diff de `articulos/` — debe corresponder a una reforma real del DOF.")
    print("- Confirma la fecha contra el [DOF](https://www.dof.gob.mx/).\n")
    print("### Después de aprobar y mergear")
    print("Regenera el enriquecimiento (solo se re-generan los artículos que cambiaron):")
    print("```bash")
    print("python -m extractor enriquecer --out .")
    print("```")
    print("\n_PR generado por el workflow `vigilar-cpeum`._")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("uso: pr_summary.py <repo-de-datos>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
