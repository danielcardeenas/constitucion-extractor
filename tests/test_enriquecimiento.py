"""Pruebas de la capa GENERADA (enriquecimiento para recall).

La generación la hace un LLM (no-determinista), así que aquí probamos lo
determinista: validación de esquema, hash/caché, extracción de JSON y que el
bloque de cuarentena `_generado` siempre esté presente. La llamada al LLM se
sustituye por un doble.
"""
from __future__ import annotations

import json

import pytest

from extractor import enrich
from extractor.parse import parse_text

VALIDO = {
    "denominacion_comun": "Derechos humanos",
    "temas": ["derechos humanos", "no discriminación"],
    "terminos_coloquiales": ["mis derechos", "discriminación"],
    "resumen": "Reconoce los derechos humanos de todas las personas.",
    "preguntas_ejemplo": ["¿Qué derechos tengo?", "¿Prohíbe la discriminación?"],
}


def art(body="Texto del artículo de prueba."):
    return parse_text(f"Artículo 1o. {body}\n")[0]


# --------------------------------------------------------------------------- #
# Hash / caché                                                                #
# --------------------------------------------------------------------------- #

def test_hash_es_estable_y_sensible_al_texto():
    assert enrich.text_hash("abc") == enrich.text_hash("abc")
    assert enrich.text_hash("abc") != enrich.text_hash("abd")


def test_needs_refresh_sin_existente():
    assert enrich.needs_refresh(art(), None) is True


def test_needs_refresh_compara_hash_del_texto():
    a = art("Texto original.")
    plain = enrich.article_plain_text(a)
    existing = {"_generado": {"hash_texto": enrich.text_hash(plain)}}
    assert enrich.needs_refresh(a, existing) is False
    # Si el texto cambia, el hash guardado deja de coincidir → hay que regenerar.
    existing_viejo = {"_generado": {"hash_texto": "sha256:0000000000000000"}}
    assert enrich.needs_refresh(a, existing_viejo) is True


# --------------------------------------------------------------------------- #
# Extracción y validación                                                     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw", [
    json.dumps(VALIDO),
    "```json\n" + json.dumps(VALIDO) + "\n```",
    "Aquí tienes el JSON:\n" + json.dumps(VALIDO) + "\n¡Listo!",
])
def test_extract_json_tolera_envoltura(raw):
    assert enrich._extract_json(raw)["denominacion_comun"] == "Derechos humanos"


def test_validate_acepta_valido():
    enrich.validate(VALIDO)  # no levanta


@pytest.mark.parametrize("mut", [
    {"denominacion_comun": ""},
    {"temas": []},
    {"temas": "no es lista"},
    {"resumen": None},
    {"preguntas_ejemplo": [1, 2]},
])
def test_validate_rechaza_invalido(mut):
    bad = {**VALIDO, **mut}
    with pytest.raises(ValueError):
        enrich.validate(bad)


# --------------------------------------------------------------------------- #
# Cuarentena: el bloque _generado siempre presente                           #
# --------------------------------------------------------------------------- #

def test_assemble_incluye_bloque_de_cuarentena():
    a = art()
    rec = enrich.assemble(a, enrich.article_plain_text(a), VALIDO, "modelo-x")
    g = rec["_generado"]
    assert g["modelo"] == "modelo-x"
    assert g["schema"] == enrich.SCHEMA_VERSION
    assert g["hash_texto"].startswith("sha256:")
    assert "no es texto oficial" in g["advertencia"].lower()
    assert rec["clave"] == "001"


def test_enrich_article_con_llm_simulado():
    a = art()
    call = lambda prompt: "```json\n" + json.dumps(VALIDO) + "\n```"
    rec = enrich.enrich_article(a, call, "modelo-x")
    assert rec["temas"] == ["derechos humanos", "no discriminación"]
    assert "_generado" in rec


# --------------------------------------------------------------------------- #
# Caché en run_enrichment: no regenera lo que no cambió                       #
# --------------------------------------------------------------------------- #

def test_caller_for_rechaza_proveedor_desconocido():
    with pytest.raises(ValueError):
        enrich.caller_for("gemini", "x")


def test_proveedores_tienen_modelo_por_defecto():
    assert "anthropic" in enrich.DEFAULT_MODELS
    assert "openai" in enrich.DEFAULT_MODELS


def test_run_enrichment_usa_cache(tmp_path):
    arts = [art()]
    llamadas = {"n": 0}

    def call(prompt):
        llamadas["n"] += 1
        return json.dumps(VALIDO)

    s1 = enrich.run_enrichment(arts, str(tmp_path), call, "modelo-x")
    assert (s1["generados"], s1["omitidos"], s1["fallidos"]) == (1, 0, 0)
    # Segunda corrida: el texto no cambió → se omite, sin nueva llamada al LLM.
    s2 = enrich.run_enrichment(arts, str(tmp_path), call, "modelo-x")
    assert (s2["generados"], s2["omitidos"], s2["fallidos"]) == (0, 1, 0)
    assert llamadas["n"] == 1                       # el LLM se llamó una sola vez
    # Con --force sí regenera.
    s3 = enrich.run_enrichment(arts, str(tmp_path), call, "modelo-x", force=True)
    assert (s3["generados"], s3["omitidos"], s3["fallidos"]) == (1, 0, 0)
    assert llamadas["n"] == 2


def test_un_articulo_que_falla_no_tumba_el_batch(tmp_path):
    # Dos artículos; el LLM devuelve algo inválido para uno → se salta, el otro sí.
    arts = [art("Texto uno."), art("Texto dos.")]
    arts[1].number = 2                              # distinto id para no chocar
    n = {"i": 0}

    def call(prompt):
        n["i"] += 1
        if "Texto dos" in prompt:
            return json.dumps({**VALIDO, "temas": []})   # inválido siempre
        return json.dumps(VALIDO)

    stats = enrich.run_enrichment(arts, str(tmp_path), call, "modelo-x", reintentos=2)
    assert stats["generados"] == 1
    assert stats["fallidos"] == 1
    assert any("002" in e for e in stats["errores"])
