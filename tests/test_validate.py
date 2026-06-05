"""Pruebas de los invariantes deterministas (el gate de un PR de reforma)."""
from __future__ import annotations

import json

from extractor.validate import parse_diff_status, validate


def make_repo(tmp, n=136):
    """Crea un repo de datos mínimo y VÁLIDO en `tmp`."""
    (tmp / "articulos").mkdir()
    (tmp / "metadata" / "segmentos").mkdir(parents=True)
    arts, pasajes = [], []
    for i in range(1, n + 1):
        clave = f"{i:03d}"
        (tmp / "articulos" / f"{clave}.md").write_text(
            f"# Artículo {i}\n\nTexto suficiente del artículo {i} para no parecer truncado.\n",
            encoding="utf-8")
        arts.append({"clave": clave, "etiqueta": f"Artículo {i}", "ultima_reforma": "2020-01-01"})
        (tmp / "metadata" / "segmentos" / f"{clave}.json").write_text(
            json.dumps({"bloques": [{"id": f"{clave}.p1", "tipo": "parrafo", "texto": "x"}]}),
            encoding="utf-8")
        pasajes.append(json.dumps({"id": f"{clave}.p1"}))
    (tmp / "metadata" / "articulos.json").write_text(
        json.dumps({"version": "2026-06-02", "articulos": arts}), encoding="utf-8")
    (tmp / "metadata" / "reformas.json").write_text(
        json.dumps({"2020-01-01": ["001"]}), encoding="utf-8")
    (tmp / "metadata" / "pasajes.jsonl").write_text("\n".join(pasajes) + "\n", encoding="utf-8")
    return tmp


def test_repo_valido_pasa(tmp_path):
    ok, checks = validate(str(make_repo(tmp_path)))
    assert ok, [c for c in checks if not c[0]]


def test_fuga_de_encabezado_falla(tmp_path):
    repo = make_repo(tmp_path)
    p = repo / "articulos" / "050.md"
    p.write_text(p.read_text() + "\nCÁMARA DE DIPUTADOS DEL H. CONGRESO\n", encoding="utf-8")
    ok, checks = validate(str(repo))
    assert not ok
    assert any(not c[0] and "fugas" in c[1] for c in checks)


def test_articulo_truncado_falla(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "articulos" / "050.md").write_text("# Artículo 50\n\n.\n", encoding="utf-8")
    ok, checks = validate(str(repo))
    assert not ok
    assert any(not c[0] and "truncado" in c[1] for c in checks)


def test_falta_un_articulo_falla(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "articulos" / "136.md").unlink()
    ok, _ = validate(str(repo))
    assert not ok


def test_pasajes_no_cuadran_falla(tmp_path):
    repo = make_repo(tmp_path)
    f = repo / "metadata" / "pasajes.jsonl"
    f.write_text(f.read_text() + json.dumps({"id": "extra"}) + "\n", encoding="utf-8")
    ok, checks = validate(str(repo))
    assert not ok
    assert any(not c[0] and "pasajes" in c[1] for c in checks)


def test_fecha_invalida_falla(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "metadata" / "reformas.json").write_text(
        json.dumps({"no-es-fecha": ["001"]}), encoding="utf-8")
    ok, checks = validate(str(repo))
    assert not ok
    assert any(not c[0] and "fechas" in c[1] for c in checks)


def test_parse_diff_status():
    texto = "M\tarticulos/004.md\nD\tarticulos/099.md\nA\tarticulos/137.md\nM\tmetadata/x.json"
    changed, deleted = parse_diff_status(texto)
    assert changed == ["004", "137"]          # ignora el .json
    assert deleted == ["099"]
