"""Pruebas del índice de pasajes (capa de ingesta para RAG con citas)."""
from __future__ import annotations

from pathlib import Path

import pytest

from extractor.parse import parse, parse_text
from extractor.passages import passages_for


def pasajes(body: str, num: int = 4, version: str = "2026-06-02"):
    label = f"Artículo {num}o." if num <= 9 else f"Artículo {num}."
    art = parse_text(f"{label} {body.strip()}\n", start=num)[0]
    return passages_for(art, version)


def by_id(ps, pid):
    return next(p for p in ps if p["id"] == pid)


class TestCitaLegal:
    def test_cita_de_parrafo(self):
        ps = pasajes("Primer párrafo del artículo.")
        assert by_id(ps, "004.p1")["cita"] == "Artículo 4o., párrafo 1"

    def test_cita_de_fraccion_en_apartado(self):
        ps = pasajes("A. Un apartado.\nI. Una fracción.\nFracción reformada DOF 30-09-2024",
                     num=2)
        assert by_id(ps, "002.A.I")["cita"] == "Artículo 2o., Apartado A, fracción I"

    def test_cita_de_inciso(self):
        ps = pasajes("I. Una fracción.\na) Un inciso.", num=2)
        assert by_id(ps, "002.I.a")["cita"] == "Artículo 2o., fracción I, inciso a)"


class TestProvenance:
    def test_campos_de_cita_verificable(self):
        p = pasajes("Texto del párrafo.\nPárrafo reformado DOF 15-11-2024")[0]
        # Todo lo necesario para una cita verificable está presente.
        for campo in ("id", "cita", "ruta", "texto", "fuente", "url_fuente",
                      "version", "vigente_desde", "archivo_texto"):
            assert p[campo], f"falta {campo}"
        assert p["version"] == "2026-06-02"
        assert p["archivo_texto"] == "articulos/004.md"

    def test_texto_embedding_lleva_contexto(self):
        p = pasajes("La mujer y el hombre son iguales.")[0]
        # El texto de embedding antepone la ruta para mejorar la recuperación.
        assert p["texto_embedding"].startswith("Artículo 4o.")
        assert p["texto"] in p["texto_embedding"]


class TestTemporal:
    def test_vigente_desde_es_la_ultima_reforma(self):
        p = pasajes("Texto.\nPárrafo reformado DOF 06-06-2019, 15-11-2024")[0]
        assert p["vigente_desde"] == "2024-11-15"
        assert p["vigente_hasta"] is None          # forward-only: vigente

    def test_bloque_original_data_de_1917(self):
        p = pasajes("Texto original sin reformas.")[0]
        assert p["vigente_desde"] == "1917-02-05"
        assert p["reformas"] == []


PDF = Path(__file__).resolve().parent.parent / "CPEUM.pdf"


@pytest.mark.skipif(not PDF.exists(), reason="CPEUM.pdf no disponible")
def test_un_pasaje_por_bloque_y_ids_unicos():
    arts = parse(str(PDF))
    ps = [p for a in arts for p in passages_for(a, "2026-06-02")]
    ids = [p["id"] for p in ps]
    assert len(ids) == len(set(ids))               # ids globalmente únicos
    assert len(ps) > 1000                            # ~1353 pasajes
