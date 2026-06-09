#!/usr/bin/env python3
"""Comentario asistido por LLM para un PR de reforma: resume y MARCA anomalías.

NO es un gate (de eso se encarga `extractor validar`). Es un asistente de
revisión: lee el diff de los artículos que cambiaron y produce un resumen en
lenguaje llano, señalando con ⚠️ lo que parezca corrupción/error de extracción
en vez de una reforma coherente. Imprime Markdown a stdout (el workflow lo
publica como comentario del PR).

Uso:  OPENAI_API_KEY=... python resumir_pr.py <repo-datos> <base-ref> [modelo]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MAX_CHARS = 4000          # por artículo, para acotar tokens del diff


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True).stdout


def diff_articulos(repo: Path, base: str) -> list[tuple[str, str]]:
    """[(clave, diff_unificado)] de los artículos que cambiaron.

    Usa el diff de git (líneas '-' quitadas, '+' agregadas): enfocado en EL
    cambio y mucho más eficiente en tokens que mandar el artículo completo.
    """
    # `--relative`: emite e interpreta rutas relativas al subdir de `repo`. Sin
    # él, en el layout anidado de los estados (repo = <estado>/constitucion, que
    # NO es la raíz del repo git) `--name-only` devolvería rutas desde la raíz y
    # el segundo `diff` las buscaría bajo el subdir → diff vacío. En el federal
    # (repo = raíz) es no-op.
    status = _git(repo, "diff", "--relative", "--name-only", base, "--", "articulos")
    out = []
    for path in status.splitlines():
        if not path.endswith(".md"):
            continue
        clave = Path(path).stem
        diff = _git(repo, "diff", "--relative", base, "--", path)
        # quitar el encabezado de git (diff --git, index, +++/---); dejar los hunks
        cuerpo = "\n".join(l for l in diff.splitlines()
                           if not l.startswith(("diff --git", "index ", "--- ", "+++ ")))
        out.append((clave, cuerpo[:MAX_CHARS]))
    return out


def build_prompt(diffs: list[tuple[str, str]], doc: str = "la Constitución") -> str:
    bloques = [f"[Artículo {clave}]\n{diff}" for clave, diff in diffs]
    cambios = "\n\n".join(bloques)
    return (
        f"Eres un asistente que ayuda a revisar cambios al texto de {doc} en un "
        "Pull Request. Abajo está el DIFF (formato git: líneas que empiezan con "
        "'-' se quitaron, con '+' se agregaron) de cada artículo que cambió.\n\n"
        "Tu tarea:\n"
        "1. Resume en lenguaje llano y breve QUÉ cambió en cada artículo (1-2 líneas).\n"
        "2. ⚠️ IMPORTANTE: si algún cambio parece un ERROR DE EXTRACCIÓN o corrupción "
        "(texto cortado, caracteres raros, pérdida de contenido, encabezados mezclados) "
        "en vez de una reforma legal coherente, márcalo con '⚠️ REVISAR' y explica por qué.\n\n"
        "Formato de salida (Markdown, consistente):\n"
        "- NO agregues un título de primer nivel ni de segundo (el comentario ya "
        "lleva encabezado).\n"
        "- Por cada artículo: una línea `**Artículo N**` en negritas y, debajo, "
        "1-2 oraciones. Sin corchetes. Separa los artículos con una línea en blanco.\n\n"
        "Sé conciso. No inventes; básate solo en el diff dado.\n\n"
        f"DIFFS:\n{cambios}"
    )


def _doc_name(perfil_name: str | None) -> str:
    """Nombre del documento para el prompt (p.ej. 'la Constitución Política del
    Estado de Jalisco'). Si no se da perfil o no se puede importar, genérico."""
    if not perfil_name:
        return "la Constitución"
    try:
        from extractor.fuentes import perfil_por_nombre
        return perfil_por_nombre(perfil_name).nombre
    except Exception:
        return "la Constitución"


def summarize(prompt: str, model: str) -> str:
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model, max_tokens=900,
        messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content or ""


def main(repo_arg: str, base: str, perfil: str | None = None,
         model: str = "gpt-4o-mini") -> int:
    repo = Path(repo_arg)
    diffs = diff_articulos(repo, base)
    if not diffs:
        print("_No hubo cambios de texto en artículos._")
        return 0
    doc = _doc_name(perfil)
    cuerpo = summarize(build_prompt(diffs, doc), model)
    # Un solo encabezado, consistente. Con perfil incluye el nombre del documento;
    # sin perfil (federal) conserva el título genérico previo.
    print(f"## 🔎 Resumen asistido — {doc}\n" if perfil
          else "## 🤖 Resumen asistido del cambio\n")
    print(cuerpo)
    print("\n---\n> Generado por IA como **apoyo de revisión** (no es un gate ni "
          "fuente de cita). El gate real es el check `validar`. Revisa el diff.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("uso: resumir_pr.py <repo-datos> <base-ref> [perfil] [modelo]",
              file=sys.stderr)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:5]))
