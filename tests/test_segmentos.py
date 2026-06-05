"""Pruebas de la descomposición en bloques con reforma enlazada (capa 3).

El objetivo de esta capa es que un LLM no infiera a qué bloque pertenece cada
nota: la asociación es dato explícito. Estas pruebas blindan esa asociación.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from extractor.parse import parse, parse_text
from extractor.segments import _classify, _note_scope, segment


def seg(body: str, number: str = "Artículo 1o.") -> dict:
    return segment(parse_text(f"{number} {body.strip()}\n")[0])


def bloque(d: dict, bid: str) -> dict:
    return next(b for b in d["bloques"] if b["id"] == bid)


# --------------------------------------------------------------------------- #
# Clasificación de marcadores                                                 #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("texto,tipo,marca", [
    ("I. Una fracción.", "fraccion", "I"),
    ("XIV. Otra fracción.", "fraccion", "XIV"),
    ("a) Un inciso.", "inciso", "a"),
    ("A. Un apartado con punto.", "apartado", "A"),
    ("A) Un apartado con paréntesis.", "apartado", "A"),
    ("C. Apartado C (no fracción 100).", "apartado", "C"),  # C romano ≠ fracción
    ("1. Un numeral.", "numeral", "1"),
    ("Texto normal sin marca.", "parrafo", ""),
])
def test_clasificacion_de_marcadores(texto, tipo, marca):
    assert _classify(texto) == (tipo, marca)


# --------------------------------------------------------------------------- #
# Alcance de la nota (la palabra define a qué refiere)                        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("nota,scope", [
    ("Párrafo reformado DOF 10-06-2011", "parrafo"),
    ("Fracción reformada DOF 30-09-2024", "fraccion"),
    ("Inciso reformado DOF 15-05-2019", "inciso"),
    ("Apartado D adicionado DOF 30-09-2024", "apartado"),
    ("Artículo reformado DOF 14-08-2001", "articulo"),
    ("Fe de erratas al párrafo DOF 09-03-1993", "parrafo"),
    ("Fracción reformada y recorrida (antes fracción V) DOF 30-09-2024", "fraccion"),
])
def test_alcance_de_la_nota(nota, scope):
    assert _note_scope(nota) == scope


# --------------------------------------------------------------------------- #
# Asociación nota ↔ bloque                                                    #
# --------------------------------------------------------------------------- #

class TestAsociacion:
    def test_nota_de_parrafo_se_ancla_al_parrafo_anterior(self):
        d = seg("Primer párrafo original.\n"
                "Segundo párrafo reformado.\nPárrafo reformado DOF 30-09-2024")
        assert "reformas" not in bloque(d, "001.p1")          # original, sin nota
        assert bloque(d, "001.p2")["reformas"][0]["fechas"] == ["2024-09-30"]

    def test_nota_de_fraccion_cubre_la_fraccion_no_el_subparrafo(self):
        # La fracción tiene un sub-párrafo; la nota 'Fracción' debe colgar de la
        # fracción completa, no del sub-párrafo.
        d = seg("I. Texto de la fracción.\n"
                "Sub-párrafo de esa misma fracción.\n"
                "Fracción reformada DOF 30-09-2024")
        f = bloque(d, "001.I")
        assert f["tipo"] == "fraccion"
        assert "Sub-párrafo" in f["texto"]                    # sub-párrafo unido
        assert f["reformas"][0]["fechas"] == ["2024-09-30"]

    def test_nota_de_articulo_no_se_cuelga_de_un_parrafo(self):
        d = seg("Único párrafo del artículo.\n"
                "Párrafo reformado DOF 10-06-2011\n"
                "Artículo reformado DOF 14-08-2001")
        # La nota de párrafo va al párrafo; la de artículo, a campo aparte.
        assert bloque(d, "001.p1")["reformas"][0]["fechas"] == ["2011-06-10"]
        assert d["reformas_articulo"][0]["fechas"] == ["2001-08-14"]
        # Y NO está dentro de ningún bloque.
        assert all("14-08-2001" not in str(b.get("reformas", "")) for b in d["bloques"])

    def test_un_bloque_puede_tener_varias_reformas(self):
        d = seg("Un párrafo.\n"
                "Fe de erratas al párrafo DOF 09-03-1993\n"
                "Párrafo reformado DOF 15-05-2019")
        fechas = [r["fechas"][0] for r in bloque(d, "001.p1")["reformas"]]
        assert fechas == ["1993-03-09", "2019-05-15"]


# --------------------------------------------------------------------------- #
# Regresión contra el PDF real                                                #
# --------------------------------------------------------------------------- #

PDF = Path(__file__).resolve().parent.parent / "CPEUM.pdf"
pdf_only = pytest.mark.skipif(not PDF.exists(), reason="CPEUM.pdf no disponible")


@pytest.fixture(scope="module")
def arts():
    return parse(str(PDF))


@pdf_only
def test_ids_unicos_en_todos_los_articulos(arts):
    for a in arts:
        ids = [b["id"] for b in segment(a)["bloques"]]
        assert len(ids) == len(set(ids)), f"ids duplicados en art {a.number}"


@pdf_only
def test_toda_nota_queda_enlazada(arts):
    """Ninguna nota de reforma debe quedar huérfana: 100% van a un bloque o al
    campo reformas_articulo."""
    from extractor.normalize import normalize_body
    for a in arts:
        notas = [l for l in normalize_body(a.body, a.label).splitlines()
                 if l.startswith("_") and l.endswith("_")]
        d = segment(a)
        enlazadas = sum(len(b.get("reformas", [])) for b in d["bloques"]) \
            + len(d["reformas_articulo"])
        assert enlazadas == len(notas), f"art {a.number}: {enlazadas} vs {len(notas)}"


@pdf_only
def test_art2_apartados_y_recorridas(arts):
    d = segment(next(a for a in arts if a.number == 2))
    apartados = [b["marca"] for b in d["bloques"] if b["tipo"] == "apartado"]
    assert apartados == ["A", "B", "C", "D"]                  # C/D no se pierden
    # Una recorrida conserva su nota textual (historial de renumeración).
    recorridas = [r["nota"] for b in d["bloques"] for r in b.get("reformas", [])
                  if "recorrida" in r["nota"]]
    assert any("antes fracción" in n for n in recorridas)
