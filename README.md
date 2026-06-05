# constitucion-extractor

Lógica de extracción que convierte el PDF oficial de la **Constitución Política
de los Estados Unidos Mexicanos** (publicado por la H. Cámara de Diputados) en
archivos Markdown limpios, listos para versionarse en el repo de datos
[`constitucion-mexicana`](../constitucion-mexicana).

Este repo contiene **solo código**. El texto de la ley vive en el repo de datos,
de modo que su historial de git sea un registro auditable de reformas, sin
contaminarse con cambios del parser.

## Arquitectura: 3 capas

```
1. Extracción fiel    PDF → texto por artículo        ← fuente de verdad
2. Detección          git diff                         ← lógica principal (no es código)
3. Enriquecimiento    fechas, mapa reforma→artículo    ← derivado, best-effort, AISLADO
```

La detección de cambios **no** es string matching: la hace git. Las regex de
fechas/notas son un *indexador* de la capa 3; si fallan, el texto sigue correcto
y git sigue viendo el cambio. Regla de oro: **la capa 3 nunca toca los archivos
de la capa 1.** Por eso `write_articles` (texto) y `write_metadata` (índice) son
independientes, y existe `index` para regenerar solo la metadata.

## Cómo funciona

```
CPEUM.pdf ─> parse.py ─> [Article] ─┬─> normalize.py ─> write_articles ─> articulos/NNN.md  (texto)
            (segmenta)              └─> reform_dates ──> write_metadata ─> metadata/*.json   (derivado)
```

1. **`parse.py`** abre el PDF con `pdfplumber`, elimina encabezados/pies de
   página, segmenta el articulado validando la secuencia 1–136 (descarta citas
   tipo *"artículo 27 de esta Constitución"*) y corta antes de los *Transitorios*.
   `reform_dates_in` extrae las fechas (`DOF DD-MM-YYYY`, incluso encadenadas).
   `parse_text` permite segmentar texto sin PDF (para tests).
2. **`normalize.py`** re-une los saltos de línea "visuales" del PDF en párrafos
   y deja las notas de reforma en *cursiva* (reensamblando las que el PDF parte
   en varias líneas), para que un `git diff` muestre solo el párrafo cambiado.
3. **`segments.py`** (capa 3) descompone cada artículo en bloques (párrafo,
   fracción, inciso, apartado) y **enlaza cada nota de reforma a su bloque** por
   alcance, para que un LLM no infiera la asociación. Las notas de alcance
   "Artículo" van a `reformas_articulo` (campo aparte). Escribe
   `metadata/segmentos/NNN.json`.
4. **`build.py`** — `write_articles` escribe el texto puro (capa 1);
   `write_metadata` escribe el índice y los segmentos en `metadata/` (capa 3).

## Uso

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Descargar el PDF vigente (o colocar uno):
curl -L -o CPEUM.pdf https://www.diputados.gob.mx/LeyesBiblio/pdf/CPEUM.pdf

# Ver estadísticas del parseo sin escribir:
.venv/bin/python -m extractor stats --pdf CPEUM.pdf

# Generar texto + metadata en el repo de datos:
.venv/bin/python -m extractor build --pdf CPEUM.pdf --out ../constitucion-mexicana

# Solo una capa:
.venv/bin/python -m extractor build --only text --pdf CPEUM.pdf --out ../constitucion-mexicana
.venv/bin/python -m extractor index --pdf CPEUM.pdf --out ../constitucion-mexicana  # solo metadata
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
