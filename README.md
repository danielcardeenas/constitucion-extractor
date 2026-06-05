# constitucion-extractor

Lógica de extracción que convierte el PDF oficial de la **Constitución Política
de los Estados Unidos Mexicanos** (publicado por la H. Cámara de Diputados) en
archivos Markdown limpios, listos para versionarse en el repo de datos
[`constitucion-mexicana`](../constitucion-mexicana).

Este repo contiene **solo código**. El texto de la ley vive en el repo de datos,
de modo que su historial de git sea un registro auditable de reformas, sin
contaminarse con cambios del parser.

## Cómo funciona

```
CPEUM.pdf ──> parse.py ──> [Article, ...] ──> normalize.py ──> build.py ──> articulos/NNN.md
              (segmenta)      (modelo)         (párrafos)        (Markdown + frontmatter)
```

1. **`parse.py`** abre el PDF con `pdfplumber`, elimina los encabezados/pies de
   página repetidos, segmenta el articulado en artículos validando la secuencia
   1–136 (descarta citas tipo *"artículo 27 de esta Constitución"*) y corta
   antes de los *Transitorios*. Extrae las fechas de reforma (`DOF DD-MM-YYYY`).
2. **`normalize.py`** re-une los saltos de línea "visuales" del PDF en párrafos
   y deja las notas de reforma en *cursiva*, para que un `git diff` de una
   reforma muestre solo el párrafo cambiado.
3. **`build.py`** escribe un archivo por artículo con frontmatter YAML
   (número, título, capítulo, fechas de reforma) y genera índices en
   `metadata/`.

## Uso

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Descargar el PDF vigente (o colocar uno):
curl -L -o CPEUM.pdf https://www.diputados.gob.mx/LeyesBiblio/pdf/CPEUM.pdf

# Ver estadísticas del parseo sin escribir:
.venv/bin/python -m extractor stats --pdf CPEUM.pdf

# Generar los Markdown en el repo de datos:
.venv/bin/python -m extractor build --pdf CPEUM.pdf --out ../constitucion-mexicana
```

## Flujo de actualización (rastro de reformas)

Cuando el DOF publica una reforma, la Cámara actualiza el PDF. Para dejar rastro:

```bash
curl -L -o CPEUM.pdf https://www.diputados.gob.mx/LeyesBiblio/pdf/CPEUM.pdf
.venv/bin/python -m extractor build --pdf CPEUM.pdf --out ../constitucion-mexicana

cd ../constitucion-mexicana
git add -A
git diff --cached            # revisar qué artículos cambiaron
git commit -m "Reforma DOF DD-MM-YYYY: arts. X, Y"
```

El `git log` del repo de datos queda como la historia de reformas; `git blame`
sobre cualquier artículo muestra cuándo y cómo cambió cada párrafo.

## Pruebas

```bash
.venv/bin/python -m pytest -q
```
