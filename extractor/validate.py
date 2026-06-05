"""Invariantes deterministas del repo de datos — el gate real de un PR de reforma.

Atrapa regresiones del parser / corrupción mejor que cualquier LLM, porque no
depende de criterio: o se cumplen los invariantes o no. Pensado para correr como
check de CI sobre el PR; sale con código != 0 si algo falla.
"""
from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

# Marcas que NUNCA deben aparecer en el texto (encabezados/pies del PDF).
LEAK_MARKERS = ("CÁMARA DE DIPUTADOS", "Secretaría de Servicios", " de 414")
N_ARTICULOS = 136
MIN_BODY_CHARS = 40            # un artículo más corto que esto está truncado/vacío


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True).stdout


def parse_diff_status(status_text: str) -> tuple[list[str], list[str]]:
    """De `git diff --name-status` → (claves_cambiadas, claves_eliminadas)."""
    changed, deleted = [], []
    for line in status_text.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        code, path = parts[0], parts[-1]
        if not path.endswith(".md"):
            continue
        clave = Path(path).stem
        if code.startswith("D"):
            deleted.append(clave)
        else:                                  # M, A, R...
            changed.append(clave)
    return changed, deleted


def validate(data_repo: str, base: str | None = None,
             max_changes: int = 20) -> tuple[bool, list[tuple[bool, str, str]]]:
    """Corre los invariantes. Devuelve (todo_ok, [(ok, etiqueta, detalle), ...])."""
    repo = Path(data_repo)
    checks: list[tuple[bool, str, str]] = []

    def chk(ok: bool, label: str, detail: str = "") -> None:
        checks.append((bool(ok), label, detail))

    # ---- estructurales (sobre el estado regenerado) --------------------- #
    md = sorted((repo / "articulos").glob("*.md"))
    chk(len(md) == N_ARTICULOS, f"{N_ARTICULOS} artículos en texto", f"hay {len(md)}")

    idx = json.loads((repo / "metadata" / "articulos.json").read_text(encoding="utf-8"))
    chk(len(idx["articulos"]) == N_ARTICULOS, f"{N_ARTICULOS} en el índice",
        f"hay {len(idx['articulos'])}")
    chk(bool(idx.get("version")), "versión del PDF registrada", str(idx.get("version")))

    cuerpos = {p.name: p.read_text(encoding="utf-8") for p in md}
    truncados = [n for n, t in cuerpos.items()
                 if len(t.split("\n", 2)[-1].strip()) < MIN_BODY_CHARS]
    chk(not truncados, "ningún artículo vacío/truncado", ", ".join(truncados[:5]))

    fugas = [n for n, t in cuerpos.items() if any(m in t for m in LEAK_MARKERS)]
    chk(not fugas, "sin fugas de encabezado/pie de página", ", ".join(fugas[:5]))

    pasajes = sum(1 for l in (repo / "metadata" / "pasajes.jsonl")
                  .read_text(encoding="utf-8").splitlines() if l.strip())
    bloques = sum(len(json.loads(s.read_text(encoding="utf-8"))["bloques"])
                  for s in (repo / "metadata" / "segmentos").glob("*.json"))
    chk(pasajes == bloques, "pasajes == bloques en segmentos", f"{pasajes} vs {bloques}")

    malas = []
    for d in json.loads((repo / "metadata" / "reformas.json").read_text(encoding="utf-8")):
        try:
            date.fromisoformat(d)
        except ValueError:
            malas.append(d)
    chk(not malas, "fechas de reforma válidas", ", ".join(malas[:5]))

    # ---- de diferencia (vs. la versión base; requiere git) -------------- #
    if base:
        changed, deleted = parse_diff_status(
            _git(repo, "diff", "--name-status", base, "--", "articulos"))
        chk(not deleted, "ningún artículo eliminado", ", ".join(deleted[:5]))
        chk(len(changed) <= max_changes,
            f"cambios acotados (≤{max_changes})",
            f"{len(changed)} artículos cambiaron"
            + (" — ¿reforma masiva o regresión del parser?" if len(changed) > max_changes else ""))

    return all(c[0] for c in checks), checks


def format_report(checks: list[tuple[bool, str, str]]) -> str:
    lines = []
    for ok, label, detail in checks:
        mark = "✓" if ok else "✗ FALLA"
        lines.append(f"  [{mark}] {label}" + (f"  — {detail}" if detail else ""))
    return "\n".join(lines)
