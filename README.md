# Ontario Grid

El mercado eléctrico de Ontario con los datos públicos de IESO: precios day-ahead y real-time de
las nueve zonas virtuales y su diferencia (DART), generación por fuente, demanda real contra el
pronóstico, interconexiones con los vecinos y la adecuación de la próxima semana.

**Sitio:** https://lulopdz.github.io/ontario-grid/

Proyecto independiente, sin afiliación con IESO.

## Cómo funciona

Todo sale de los reportes públicos de IESO (https://reports-public.ieso.ca/public/): sin API
keys ni cupos. Una GitHub Action (`.github/workflows/update.yml`) corre cada hora:

1. `ingest/update.py` trae lo nuevo y vuelve a pedir lo que falte de los últimos 7 días, así un
   reporte que IESO publicó tarde se completa en la corrida siguiente.
2. Los CSV de `data/` se commitean si cambiaron.
3. `build.py` arma el sitio en `_site/` (un JSON compacto por vista, los CSV para descargar y
   plotly.js) y se publica en GitHub Pages.

| Archivo | Contenido | Desde |
|---|---|---|
| `data/prices.csv` | Precio day-ahead y real-time (promedio de los 12 intervalos de 5 min) por zona, $/MWh | 2025-05-20 |
| `data/generation.csv` | Generación por fuente, MW | 2018 |
| `data/demand.csv` | Demanda de Ontario y de mercado (con exportaciones), MW | 2018 |
| `data/interties.csv` | Importación y exportación programadas y flujo real por vecino, MW (flujo > 0: Ontario exporta) | 2018 |
| `data/adequacy.csv` | Pronóstico de demanda, capacidad de suministro, requerido y margen: el último pronóstico publicado antes de empezar cada día | 2026-09-17 |
| `data/adequacy_outlook.csv` | Lo mismo para hoy y los 6 días siguientes, según el pronóstico más reciente | — |

Todas las horas van en hora de mercado de IESO: EST todo el año, sin horario de verano; `he` es
la hora que termina (1-24).

IESO mantiene en línea unos 3 meses de reportes diarios (precios, adecuación). La historia de
precios anterior viene de [lrg-dashboard](https://github.com/lulopdz/lrg-dashboard) (GridStatus,
verificada contra estos mismos reportes). Generación, demanda e interconexiones tienen archivos
anuales, así que su historia completa siempre se puede reconstruir:

```bash
pip install -r requirements.txt
python ingest/update.py --window 100 --full-years   # todo lo que IESO todavía tiene
python build.py                                     # sitio en _site/
```
