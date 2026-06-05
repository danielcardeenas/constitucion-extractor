"""Pruebas del manejo de reformas y del flujo de actualización.

No requieren el PDF: alimentan texto sintético (con el mismo formato que el
PDF ya limpio) directamente a `parse_text`, lo que permite simular reformas
y verificar que el `git diff` resultante sea limpio y localizado.
"""
from __future__ import annotations

import difflib
import re

import pytest

from extractor.build import render_markdown
from extractor.normalize import normalize_body
from extractor.parse import parse_text

# Una línea de cuerpo nunca debe empezar con una fecha suelta: significaría que
# la cola de una nota envuelta se filtró al texto del artículo.
LEAKED_DATE_LINE = re.compile(r"(?m)^(?:DOF\s+)?\d{2}-\d{2}-\d{4}")


def render(body_lines: str, number: str = "Artículo 1o.") -> str:
    """Envuelve texto crudo como un artículo y devuelve su Markdown."""
    arts = parse_text(f"{number} {body_lines.strip()}\n")
    assert arts, "el texto sintético no produjo ningún artículo"
    return render_markdown(arts[0])


def article(body_lines: str):
    return parse_text(f"Artículo 1o. {body_lines.strip()}\n")[0]


def changed_lines(before: str, after: str):
    """Líneas agregadas/quitadas entre dos versiones (sin contexto)."""
    added, removed = [], []
    for line in difflib.unified_diff(before.splitlines(), after.splitlines(), n=0):
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            removed.append(line[1:])
    return added, removed


# --------------------------------------------------------------------------- #
# Formas de las notas de reforma                                              #
# --------------------------------------------------------------------------- #

class TestFormasDeNotas:
    def test_nota_simple_va_en_cursiva(self):
        md = render("Texto del artículo.\nArtículo reformado DOF 14-08-2001")
        assert "_Artículo reformado DOF 14-08-2001_" in md

    def test_nota_multifecha_se_renderiza_completa(self):
        md = render("Texto.\nPárrafo reformado DOF 04-12-2006, 10-06-2011")
        assert "_Párrafo reformado DOF 04-12-2006, 10-06-2011_" in md

    def test_nota_compuesta_recorrida(self):
        # El ejemplo exacto del caso de uso.
        nota = ("Fracción reformada DOF 06-06-2019. Reformada y recorrida "
                "(antes fracción VII) DOF 30-09-2024")
        md = render(f"I. Una fracción.\n{nota}")
        assert f"_{nota}_" in md

    def test_nota_envuelta_en_varias_lineas_se_reensambla(self):
        # Como el art. 73: la nota es tan larga que el PDF la parte.
        raw = ("XI. Para crear empleos.\n"
               "Fracción reformada DOF 06-09-1929, 27-04-1933, 18-01-1934, 14-12-1940, \n"
               "17-11-1982, 20-08-1993, 20-07-2007")
        md = render(raw)
        assert ("_Fracción reformada DOF 06-09-1929, 27-04-1933, 18-01-1934, "
                "14-12-1940, 17-11-1982, 20-08-1993, 20-07-2007_") in md

    def test_nota_envuelta_con_clausula_recorrida(self):
        raw = ("XXV. Una fracción.\n"
               "Fracción reformada DOF 08-07-1921. Recorrida (antes fracción XXVII) por\n"
               "derogación de fracciones DOF 13-12-1934, 15-05-2019")
        md = render(raw)
        nota = next(l for l in md.splitlines() if l.startswith("_Fracción reformada DOF 08-07-1921"))
        assert nota.endswith("15-05-2019_")
        assert "13-12-1934" in nota

    @pytest.mark.parametrize("nota", [
        "Artículo reformado DOF 14-08-2001",
        "Párrafo reformado DOF 04-12-2006, 10-06-2011",
        "Fracción adicionada DOF 30-09-2024",
        "Inciso reformado DOF 09-02-2012, 26-02-2013, 15-05-2019",
        "Fracción reformada y recorrida (antes fracción V) DOF 30-09-2024",
        "Fe de erratas al párrafo DOF 09-03-1993. Reformado DOF 12-11-2002, 15-05-2019",
    ])
    def test_ninguna_nota_se_filtra_al_cuerpo(self, nota):
        md = render(f"Texto base del artículo.\n{nota}")
        body = md.split("---", 2)[-1]
        assert not LEAKED_DATE_LINE.search(body), f"fuga de fecha con: {nota}"
        assert f"_{nota}_" in md


# --------------------------------------------------------------------------- #
# Extracción de fechas (alimenta el frontmatter y el rastro)                  #
# --------------------------------------------------------------------------- #

class TestExtraccionDeFechas:
    def test_todas_las_fechas_de_una_nota_multifecha(self):
        a = article("Texto.\nPárrafo reformado DOF 04-12-2006, 10-06-2011")
        assert [d.isoformat() for d in a.reform_dates] == ["2006-12-04", "2011-06-10"]

    def test_fechas_de_nota_compuesta(self):
        a = article("I. X.\nFracción reformada DOF 06-06-2019. Reformada y recorrida "
                    "(antes fracción VII) DOF 30-09-2024")
        assert [d.isoformat() for d in a.reform_dates] == ["2019-06-06", "2024-09-30"]

    def test_ultima_reforma_es_la_mas_reciente(self):
        a = article("Texto.\nArtículo reformado DOF 14-08-2001, 10-06-2011, 30-09-2024")
        assert a.last_reform.isoformat() == "2024-09-30"

    def test_fechas_se_deduplican_y_ordenan(self):
        a = article("Texto.\nPárrafo reformado DOF 10-06-2011\n"
                    "Otro párrafo.\nFracción reformada DOF 10-06-2011, 14-08-2001")
        assert [d.isoformat() for d in a.reform_dates] == ["2001-08-14", "2011-06-10"]

    def test_articulo_sin_reformas_no_tiene_ultima(self):
        a = article("Texto original sin reformas.")
        assert a.reform_dates == []
        assert a.last_reform is None


# --------------------------------------------------------------------------- #
# Flujo de actualización: una reforma produce un diff limpio y localizado     #
# --------------------------------------------------------------------------- #

class TestUpdatesDiff:
    BASE = ("Primer párrafo que no cambia con esta reforma.\n"
            "Toda persona tiene derecho a la salud.\n"
            "Párrafo adicionado DOF 06-06-2019\n"
            "Tercer párrafo que tampoco cambia.")

    def test_reforma_de_un_parrafo_solo_toca_ese_parrafo(self):
        before = render(self.BASE)
        after = render(self.BASE.replace(
            "derecho a la salud.\nPárrafo adicionado DOF 06-06-2019",
            "derecho a la salud y al deporte.\n"
            "Párrafo adicionado DOF 06-06-2019. Reformado DOF 30-09-2024",
        ))
        added, removed = changed_lines(before, after)
        # El párrafo reformado y su nota cambian; el resto no.
        assert any("al deporte" in l for l in added)
        assert all("Primer párrafo que no cambia" not in l for l in added + removed)
        assert all("Tercer párrafo que tampoco" not in l for l in added + removed)

    def test_reforma_actualiza_frontmatter(self):
        before = render(self.BASE)
        after = render(self.BASE.replace(
            "Párrafo adicionado DOF 06-06-2019",
            "Párrafo adicionado DOF 06-06-2019. Reformado DOF 30-09-2024",
        ))
        assert "ultima_reforma: 2019-06-06" in before
        assert "ultima_reforma: 2024-09-30" in after
        assert "2024-09-30" not in before
        assert "reformas: [2019-06-06, 2024-09-30]" in after

    def test_agregar_una_fraccion_inserta_limpio(self):
        before = render("I. Primera fracción.\nII. Segunda fracción.")
        after = render("I. Primera fracción.\nII. Segunda fracción.\n"
                       "III. Tercera fracción nueva.\nFracción adicionada DOF 30-09-2024")
        added, removed = changed_lines(before, after)
        # Las fracciones previas no se tocan; solo se inserta la nueva (el
        # frontmatter sí cambia porque la reforma agregó una fecha).
        assert all("fracción" not in l.lower() for l in removed)
        assert any("Tercera fracción nueva" in l for l in added)

    def test_build_es_idempotente(self):
        # Reconstruir sin cambios debe dar exactamente el mismo Markdown,
        # para que un rebuild sin reforma no genere "ruido" en git.
        assert render(self.BASE) == render(self.BASE)
