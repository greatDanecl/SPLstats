# Dashboard SPL · GitHub Pages

Dashboard estático para el Sindicato de Pilotos de Latam Airlines - SPL.

Este proyecto no usa Streamlit. GitHub Actions lee los Excel de `data/raw`, valida integridad, clasifica la operación por piloto y genera un sitio estático en `public/index.html`, que se publica automáticamente en GitHub Pages.

## Lógica de flota / tipo de operación

La columna de origen `aircraft_type_desc` o `Fleet` puede venir vacía en filas sin vuelo. La clasificación se hace así:

- Valores que contienen `787` → `Wide Body`.
- Valores que comienzan por `32`, por ejemplo `32N`, `32A`, `32Q`, etc. → `Narrow Body`.
- Para cada piloto se usa la moda de la flota en sus filas de vuelo con dato.
- Esa clasificación se propaga a todas sus filas, incluyendo días libres, vacaciones, licencias y filas de archivos antiguos sin flota.
- Si un piloto no tiene vuelos con flota en ningún archivo queda como `Sin clasificar`.

## Primer filtro obligatorio

La primera vista del dashboard queda vacía. El usuario debe escoger primero:

1. Flota / tipo de operación: `Wide Body` o `Narrow Body`.
2. Cargo: `CP` o `FO`, según datos disponibles.
3. Trabajador: `Overview general` o un trabajador específico.
4. Mes: parte por el más reciente disponible.

Los promedios de comparación se calculan siempre por el mismo cargo y la misma operación. Es decir, no mezcla CP Wide con CP Narrow, ni FO Wide con FO Narrow.

## Integridad de datos

El dashboard incluye una sección de integridad con:

- Archivos leídos.
- Filas normalizadas.
- Pilotos clasificados por habilitación.
- Pilotos sin clasificación.
- Pilotos con flota mixta detectada.
- Filas con actividad no clasificada.
- Filas por archivo.
- Dotación por operación y cargo.

## Publicación en GitHub Pages

En GitHub, ir a:

`Settings → Pages → Build and deployment → Source → GitHub Actions`

Luego cada push a `main` que modifique `data/raw`, `app`, `assets` o el workflow reconstruirá el dashboard.

## Estructura

```text
app/
  parser.py          # normalización, clasificación de códigos y flota
  build_static.py    # genera public/index.html
assets/
  logo.png
data/raw/
  *.xlsx
.github/workflows/
  build-data.yml
requirements.txt
public/
  index.html         # generado por GitHub Actions
```

## Dependencias

```txt
pandas
numpy
openpyxl
```

No requiere `streamlit` ni `pyarrow`.
