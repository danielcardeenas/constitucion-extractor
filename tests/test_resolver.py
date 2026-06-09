"""Pruebas del resolver de PDF vigente (scripts/resolver_pdf.py).

La descarga real es no-determinista (depende del sitio del congreso), así que
aquí probamos lo determinista: que de un índice con varias versiones se elija la
de FECHA más reciente, y que la URL salga absoluta y bien percent-encodeada.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "scripts" / "resolver_pdf.py"
_spec = importlib.util.spec_from_file_location("resolver_pdf", _MOD)
resolver_pdf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(resolver_pdf)


JAL = resolver_pdf.RESOLVERS["jalisco"]

# Índice con DOS versiones de la Constitución (vieja y nueva) + una ley ajena
# que NO debe colarse. Refleja la estructura real del "Listado Completo".
HTML_INDICE = (
    '<a href="../legislacion/Leyes/Documentos_PDF-Leyes/'
    'Ley Org\xe1nica del Poder Legislativo-071024.pdf">Ley</a>'
    '<a href="../legislacion/Constituci\xf3n/Documentos_PDF-Constituci\xf3n/'
    'Constituci\xf3n Pol\xedtica del Estado de Jalisco-180423.pdf">vieja</a>'
    '<a href="../legislacion/Constituci\xf3n/Documentos_PDF-Constituci\xf3n/'
    'Constituci\xf3n Pol\xedtica del Estado de Jalisco-241125.pdf">vigente</a>'
)


def test_elige_la_version_mas_reciente():
    url = resolver_pdf.elegir_mas_reciente(HTML_INDICE, JAL["patron"], JAL["index_url"])
    assert "-241125.pdf" in url          # 24-11-2025, no la de 18-04-2023
    assert "-180423" not in url


def test_url_absoluta_y_encodeada():
    url = resolver_pdf.elegir_mas_reciente(HTML_INDICE, JAL["patron"], JAL["index_url"])
    assert url.startswith("https://congresoweb.congresojal.gob.mx/")
    assert ".." not in url               # relativo resuelto contra el índice
    assert " " not in url                # espacios percent-encodeados
    assert "%C3%B3" in url               # 'ó' (Constitución) encodeada en UTF-8


def test_no_confunde_otras_leyes():
    # Solo un PDF de "Ley" (sin Constitución) → debe fallar, no devolver la ley.
    solo_leyes = ('<a href="../legislacion/Leyes/Documentos_PDF-Leyes/'
                  'Ley de Ingresos-300126.pdf">x</a>')
    import pytest
    with pytest.raises(SystemExit):
        resolver_pdf.elegir_mas_reciente(solo_leyes, JAL["patron"], JAL["index_url"])
