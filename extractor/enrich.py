"""Capa GENERADA (best-effort) — enriquecimiento para mejorar el recall del RAG.

⚠️  Esto es contenido generado por un LLM. NO es texto oficial ni fuente de
cita. Su único propósito es AYUDAR A RECUPERAR el pasaje correcto cuando el
usuario pregunta con lenguaje coloquial ("¿puedo abortar?", "¿pensión?"). La
respuesta y la cita SIEMPRE provienen del texto fiel (articulos/NNN.md) y de
los pasajes (metadata/pasajes.jsonl), nunca de aquí.

Disciplina de cuarentena:
- Vive en `metadata/generado/`, separado de las capas derivadas deterministas.
- Cada archivo lleva un bloque `_generado` con el modelo, el esquema y un
  `hash_texto` para regenerar solo cuando el texto del artículo cambió.
- La llamada al LLM se inyecta (`call`), para que producción use la API de
  Anthropic y los tests usen un doble determinista.
"""
from __future__ import annotations

import hashlib
import json
import re

from .parse import Article
from .segments import segment

SCHEMA_VERSION = 1
ADVERTENCIA = (
    "Contenido generado por IA como AYUDA DE RECUPERACIÓN. No es texto oficial "
    "ni fuente de cita; la verdad está en el archivo de texto del artículo."
)

# Campos que el LLM debe producir y sus tipos.
CAMPOS_LISTA = ("temas", "terminos_coloquiales", "preguntas_ejemplo")
CAMPOS_TEXTO = ("denominacion_comun", "resumen")


def article_plain_text(art: Article) -> str:
    """Texto legal del artículo sin notas de reforma (lo que ve el LLM)."""
    bloques = segment(art)["bloques"]
    return "\n\n".join(b["texto"] for b in bloques)


def text_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_prompt(label: str, plain_text: str) -> str:
    return f"""Eres un asistente que prepara METADATOS DE BÚSQUEDA para un buscador
de la Constitución mexicana. NO interpretas la ley ni das opiniones legales.

A partir del texto del {label}, devuelve SOLO un objeto JSON (sin texto extra)
con estas claves, en español, para ayudar a que una persona ENCUENTRE este
artículo cuando pregunte con palabras coloquiales:

- "denominacion_comun": nombre corto y común del tema del artículo (string).
- "temas": 4-10 temas/derechos que trata (array de strings cortos).
- "terminos_coloquiales": cómo la gente se refiere a estos temas en lenguaje
  cotidiano, incluyendo búsquedas típicas (array de strings).
- "resumen": 1-3 oraciones en lenguaje llano de lo que establece (string).
- "preguntas_ejemplo": 3-6 preguntas reales que este artículo respondería
  (array de strings).

Reglas estrictas:
- Apégate al contenido del texto; no inventes derechos que no aparezcan.
- No cites fechas ni números de reforma.
- Devuelve únicamente el JSON.

Texto del {label}:
\"\"\"
{plain_text}
\"\"\""""


def _extract_json(raw: str) -> dict:
    """Tolera que el LLM envuelva el JSON en ```json ... ``` o texto."""
    raw = raw.strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError("la respuesta del LLM no contiene JSON")
    return json.loads(m.group(0))


def validate(data: dict) -> None:
    for k in CAMPOS_TEXTO:
        if not isinstance(data.get(k), str) or not data[k].strip():
            raise ValueError(f"campo '{k}' debe ser texto no vacío")
    for k in CAMPOS_LISTA:
        v = data.get(k)
        if not isinstance(v, list) or not v or not all(isinstance(x, str) for x in v):
            raise ValueError(f"campo '{k}' debe ser lista de strings no vacía")


def assemble(art: Article, plain_text: str, data: dict, modelo: str) -> dict:
    """Arma el registro final con el bloque de cuarentena `_generado`."""
    validate(data)
    return {
        "clave": art.key,
        "etiqueta": art.label,
        "_generado": {
            "modelo": modelo,
            "schema": SCHEMA_VERSION,
            "hash_texto": text_hash(plain_text),
            "advertencia": ADVERTENCIA,
        },
        "denominacion_comun": data["denominacion_comun"].strip(),
        "temas": [t.strip() for t in data["temas"]],
        "terminos_coloquiales": [t.strip() for t in data["terminos_coloquiales"]],
        "resumen": data["resumen"].strip(),
        "preguntas_ejemplo": [q.strip() for q in data["preguntas_ejemplo"]],
    }


def needs_refresh(art: Article, existing: dict | None) -> bool:
    """True si hay que (re)generar: no existe, o el texto del artículo cambió."""
    if not existing:
        return True
    plain = article_plain_text(art)
    return existing.get("_generado", {}).get("hash_texto") != text_hash(plain)


def enrich_article(art: Article, call, modelo: str) -> dict:
    """Genera el enriquecimiento de un artículo. `call`: prompt -> respuesta cruda."""
    plain = article_plain_text(art)
    data = _extract_json(call(build_prompt(art.label, plain)))
    return assemble(art, plain, data, modelo)


# --------------------------------------------------------------------------- #
# Orquestación e integración con la API de Anthropic (producción)             #
# --------------------------------------------------------------------------- #

MANIFEST = """# metadata/generado/ — contenido GENERADO por IA (no canónico)

⚠️  Estos archivos los produce un LLM y sirven SOLO para mejorar la búsqueda
(recall) cuando alguien pregunta con lenguaje coloquial. **No son texto oficial
ni fuente de cita.** La verdad está en `articulos/NNN.md`; las citas, en
`metadata/pasajes.jsonl`.

Cada archivo trae un bloque `_generado` con el modelo, el esquema y un
`hash_texto`. Se regenera solo cuando cambia el texto del artículo
(`extractor enriquecer`).
"""


# Modelo por defecto de cada proveedor (se puede sobreescribir con --modelo).
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o-mini",          # económico; bueno para esta tarea de metadatos
}


def anthropic_caller(model: str):
    """Devuelve un `call(prompt)->str` que usa la API de Anthropic.

    Requiere `pip install anthropic` y la variable ANTHROPIC_API_KEY.
    """
    import anthropic  # import perezoso: la librería solo se necesita en producción

    client = anthropic.Anthropic()

    def call(prompt: str) -> str:
        msg = client.messages.create(
            model=model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")

    return call


def openai_caller(model: str):
    """Devuelve un `call(prompt)->str` que usa la API de OpenAI.

    Requiere `pip install openai` y la variable OPENAI_API_KEY. Usa el modo
    JSON nativo (el prompt ya pide 'un objeto JSON').
    """
    from openai import OpenAI  # import perezoso

    client = OpenAI()

    def call(prompt: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=1500,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""

    return call


def caller_for(proveedor: str, model: str):
    """Selecciona el caller según el proveedor ('anthropic' | 'openai')."""
    if proveedor == "anthropic":
        return anthropic_caller(model)
    if proveedor == "openai":
        return openai_caller(model)
    raise ValueError(f"proveedor desconocido: {proveedor!r} (usa 'anthropic' u 'openai')")


def run_enrichment(arts, data_repo, call, modelo: str, force: bool = False,
                   reintentos: int = 2) -> dict:
    """Genera/actualiza el enriquecimiento de los artículos que lo necesitan.

    Best-effort y resiliente: si el LLM devuelve algo inválido para un artículo,
    se reintenta `reintentos` veces y, si aún falla, se SALTA ese artículo sin
    abortar el batch (esta capa nunca es crítica). Usa caché por hash: omite los
    artículos cuyo texto no cambió desde la última generación.

    Devuelve stats: {"generados", "omitidos", "fallidos", "errores"}.
    """
    from pathlib import Path

    gen_dir = Path(data_repo) / "metadata" / "generado"
    gen_dir.mkdir(parents=True, exist_ok=True)
    (gen_dir / "README.md").write_text(MANIFEST, encoding="utf-8")

    generados = omitidos = fallidos = 0
    errores: list[str] = []
    for art in arts:
        path = gen_dir / f"{art.key}.json"
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if not force and not needs_refresh(art, existing):
            omitidos += 1
            continue

        record = None
        ultimo_error = None
        for _ in range(max(1, reintentos)):
            try:
                record = enrich_article(art, call, modelo)
                break
            except Exception as e:               # LLM no-determinista: reintenta
                ultimo_error = e
        if record is None:
            fallidos += 1
            errores.append(f"{art.key}: {ultimo_error}")
            continue

        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        generados += 1
    return {"generados": generados, "omitidos": omitidos,
            "fallidos": fallidos, "errores": errores}
