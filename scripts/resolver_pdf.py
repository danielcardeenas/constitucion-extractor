#!/usr/bin/env python3
"""Resuelve la URL del PDF VIGENTE de la constitución de un estado.

El problema que resuelve: a diferencia del DOF federal (URL fija), los congresos
estatales no exponen una URL estable. Hay dos patrones:

  - "directo":  el PDF vive en una URL con nombre estable (p.ej. CDMX). Se
                devuelve tal cual.
  - "indice":   el PDF lleva la FECHA embebida en el nombre y rota en cada
                reforma (p.ej. Jalisco: ...-DDMMYY.pdf). Hay que leer la página
                índice de leyes, extraer el enlace de la Constitución y quedarse
                con el de fecha más reciente.

Solo usa la librería estándar (urllib) para no añadir dependencias al CI.

Uso:
    python scripts/resolver_pdf.py jalisco        # imprime la URL vigente
    python scripts/resolver_pdf.py --listar       # estados soportados
"""
from __future__ import annotations

import re
import sys
from datetime import date
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# estado → cómo encontrar su PDF vigente.
RESOLVERS: dict[str, dict] = {
    # CDMX: vigilancia MANUAL por ahora.
    # - El PDF del piloto salió de una URL hash (media/documentos/<hash>.pdf) que
    #   rota en cada subida → no sirve como fuente durable.
    # - Sí existe una URL de nombre estable (`url_estable`) y de hecho es más
    #   limpia (sin las fugas de encabezado del piloto), PERO el perfil `cdmx`
    #   aún mis-segmenta su numeración "1. 2. 3." (deja un artículo truncado que
    #   el gate `validar` rechaza). Hasta afinar el perfil y re-basar el texto,
    #   CDMX no se auto-vigila para no abrir PRs en rojo cada semana.
    "cdmx": {
        "tipo": "manual",
        "url_estable": ("https://www.congresocdmx.gob.mx/archivos/legislativas/"
                        "constitucion_politica_de_la_ciudad_de_mexico.pdf"),
    },
    # Jalisco: el PDF lleva la fecha (DDMMYY) en el nombre y rota en cada
    # reforma. El "Listado Completo" de la biblioteca virtual enlaza al vigente.
    "jalisco": {
        "tipo": "indice",
        "index_url": ("https://congresoweb.congresojal.gob.mx/"
                      "bibliotecavirtual/busquedasleyes/Listado'2.cfm"),
        "encoding": "iso-8859-1",
        # ruta relativa del PDF de la Constitución, con DDMMYY al final.
        "patron": re.compile(
            r'href="(\.\./legislacion/[^"]*Documentos_PDF-Constituci[^"]*'
            r'-(\d{2})(\d{2})(\d{2})\.pdf)"'),
    },
}


def _fetch_text(url: str, encoding: str) -> str:
    req = Request(url, headers={"User-Agent": _UA})
    with urlopen(req, timeout=60) as r:               # nosec: URL fija de config
        return r.read().decode(encoding, errors="replace")


def _encode_url(url: str) -> str:
    """Percent-encode solo la ruta (espacios y acentos) dejando el resto igual."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=quote(parts.path, safe="/%")))


def elegir_mas_reciente(html: str, patron: re.Pattern, index_url: str) -> str:
    """Del índice `html`, devuelve la URL absoluta (codificada) del PDF de la
    Constitución con la fecha DDMMYY más reciente. Función pura (testeable)."""
    matches = patron.findall(html)
    if not matches:
        raise SystemExit(f"no se encontró el PDF de la Constitución en {index_url}")
    # Cada match: (ruta_relativa, DD, MM, YY). Quédate con la fecha más reciente.
    rel = max(matches, key=lambda m: date(2000 + int(m[3]), int(m[2]), int(m[1])))[0]
    return _encode_url(urljoin(index_url, rel))


def _resolver_indice(cfg: dict) -> str:
    html = _fetch_text(cfg["index_url"], cfg.get("encoding", "utf-8"))
    return elegir_mas_reciente(html, cfg["patron"], cfg["index_url"])


def resolver(estado: str) -> str:
    cfg = RESOLVERS.get(estado)
    if cfg is None:
        raise SystemExit(
            f"estado desconocido: {estado!r}. Soportados: {', '.join(RESOLVERS)}")
    if cfg["tipo"] == "manual":
        return ""                       # sin URL automática → el watcher lo salta
    if cfg["tipo"] == "directo":
        return cfg["url"]
    if cfg["tipo"] == "indice":
        return _resolver_indice(cfg)
    raise SystemExit(f"tipo de resolver desconocido: {cfg['tipo']!r}")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--listar":
        for e, c in RESOLVERS.items():
            print(f"{e}\t{c['tipo']}")
        return 0
    print(resolver(argv[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
