"""Fija el comportamiento del motor multi-fuente (CPEUM + perfiles estatales).

No depende de PDFs: usa texto sintético vía `parse_text`. Cubre las diferencias
que la Fase 0 detectó entre la federal y las constituciones estatales.
"""
from __future__ import annotations

from extractor.parse import parse_text
from extractor.passages import passages_for
from extractor.perfil import CPEUM, perfil_estatal
from extractor.fuentes import CDMX, JALISCO

# Perfil estatal genérico para las pruebas (gate monotónico, regex Title/UPPER).
ESTADO = perfil_estatal(
    ambito="prueba", clave="prb", nombre="Constitución de Prueba",
    fuente="Periódico Oficial de Prueba", url_fuente="https://example.test",
    texto_original="1900-01-01",
)


def _texto(*lineas: str) -> str:
    return "\n".join(lineas) + "\n"


# --- el gate: la diferencia que rompía Jalisco ------------------------------

def test_gate_estricto_federal_se_detiene_en_hueco():
    """Federal: un hueco (artículo derogado) detiene la secuencia (por diseño)."""
    txt = _texto("Artículo 1o. Uno.", "Artículo 2o. Dos.", "Artículo 4o. Cuatro.")
    nums = [a.number for a in parse_text(txt, perfil=CPEUM)]
    assert nums == [1, 2]          # el 4 se descarta: no es el esperado (3)


def test_gate_monotonico_estatal_tolera_hueco_por_derogacion():
    """Estatal: el gate monotónico salta el hueco y sigue (caso art. 6 de Jalisco)."""
    txt = _texto("Artículo 1º Uno.", "Artículo 2º Dos.", "Artículo 4º Cuatro.")
    nums = [a.number for a in parse_text(txt, perfil=ESTADO)]
    assert nums == [1, 2, 4]


def test_estatal_ignora_cita_en_minuscula():
    """'artículo 50 ...' (minúscula) es CITA, no encabezado: no debe crear art. 50.

    Era el bug que tragaba 37 artículos de Jalisco con IGNORECASE a ciegas.
    """
    txt = _texto(
        "Artículo 1º Primero.",
        "lo dispuesto en el artículo 50 de la Ley General se aplica aquí.",
        "Artículo 2º Segundo.",
    )
    nums = [a.number for a in parse_text(txt, perfil=ESTADO)]
    assert nums == [1, 2]          # nunca aparece el 50


def test_estatal_acepta_encabezado_en_mayusculas():
    """CDMX marca los artículos en MAYÚSCULAS: 'ARTÍCULO 2'."""
    txt = _texto("ARTÍCULO 1 Uno.", "ARTÍCULO 2 Dos.")
    nums = [a.number for a in parse_text(txt, perfil=CDMX)]
    assert nums == [1, 2]


def test_estatal_variante_bis():
    txt = _texto("Artículo 35º Treinta y cinco.", "Artículo 35º Bis Bis.",
                 "Artículo 36º Treinta y seis.")
    arts = parse_text(txt, perfil=ESTADO)
    assert [(a.number, a.suffix) for a in arts] == [(35, ""), (35, "Bis"), (36, "")]
    assert arts[1].key == "035-bis"


# --- contrato hacia el RAG: ambito + ids prefijados -------------------------

def test_pasajes_estatales_prefijados_y_con_ambito():
    art = parse_text(_texto("Artículo 1º Texto del artículo de prueba, suficientemente largo."),
                     perfil=ESTADO)[0]
    p = passages_for(art, "2026-06-08", perfil=ESTADO)[0]
    assert p["id"].startswith("prb:")
    assert p["ambito"] == "prueba"
    assert p["fuente"] == "Periódico Oficial de Prueba"


def test_pasajes_federales_sin_prefijo():
    art = parse_text(_texto("Artículo 1o. Texto del artículo federal, suficientemente largo."),
                     perfil=CPEUM)[0]
    p = passages_for(art, "2026-06-02", perfil=CPEUM)[0]
    assert not p["id"].startswith(":") and ":" not in p["id"]
    assert p["ambito"] == "federal"


# --- etiqueta según el estilo ordinal de la fuente --------------------------

def test_etiqueta_por_estilo_ordinal():
    fed = parse_text(_texto("Artículo 1o. x."), perfil=CPEUM)[0]
    jal = parse_text(_texto("Artículo 1º x."), perfil=JALISCO)[0]
    cmx = parse_text(_texto("ARTÍCULO 1 x."), perfil=CDMX)[0]
    assert fed.label == "Artículo 1o."
    assert jal.label == "Artículo 1º"
    assert cmx.label == "Artículo 1"
