"""Pruebas de regresión del parser contra el PDF oficial de la CPEUM.

Ejecutar:  .venv/bin/python -m pytest -q
(El PDF CPEUM.pdf debe estar en la raíz del repo del extractor.)
"""
from pathlib import Path

import pytest

from extractor.normalize import normalize_body
from extractor.parse import parse

PDF = Path(__file__).resolve().parent.parent / "CPEUM.pdf"

pytestmark = pytest.mark.skipif(not PDF.exists(), reason="CPEUM.pdf no disponible")


@pytest.fixture(scope="module")
def arts():
    return parse(str(PDF))


def test_cuenta_136_articulos(arts):
    nums = [a.number for a in arts]
    assert min(nums) == 1 and max(nums) == 136


def test_sin_huecos_en_la_secuencia(arts):
    nums = {a.number for a in arts}
    assert [n for n in range(1, 137) if n not in nums] == []


def test_sin_duplicados(arts):
    claves = [a.key for a in arts]
    assert len(claves) == len(set(claves))


def test_articulo_136_no_arrastra_transitorios(arts):
    a136 = next(a for a in arts if a.number == 136)
    # El texto vigente del 136 es corto; si arrastrara transitorios sería enorme.
    assert len(a136.body) < 1500


def test_no_quedan_encabezados_ni_pies(arts):
    for a in arts:
        assert "CÁMARA DE DIPUTADOS" not in a.body
        assert "de 414" not in a.body


def test_normalizacion_extrae_reformas(arts):
    a1 = next(a for a in arts if a.number == 1)
    assert a1.last_reform is not None
    body = normalize_body(a1.body, a1.label)
    assert body.startswith("En los Estados Unidos Mexicanos")
    assert "_Artículo reformado DOF" in body  # nota de reforma en cursiva
