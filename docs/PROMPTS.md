# Prompts para seguir el trabajo

Prompts listos para pegar en una sesión nueva de Claude Code sobre este repo
(`lulopdz/ontario-grid`). Una sesión nueva no recuerda las anteriores: cada prompt trae el
contexto que necesita, y el README explica la estructura, los datos y el workflow.

Estado al 2026-11-01: sitio en https://lulopdz.github.io/ontario-grid/ (inglés por defecto, ES
con el botón) con las pestañas Prices, Generation, Demand, Interties y Virtuals. El workflow
"Update and publish" corre cada hora (el horario de GitHub se atrasa o se salta horas; cada
corrida vuelve a pedir lo que falte de los últimos 7 días). Los datos de mercado que IESO borra
a los ~30 días se archivan por mes desde el 2026-10-31.

## Reglas que valen para todos

> Lee el README antes de tocar nada. Los datos van siempre a CSV por hora en `data/`: los cuatro
> grandes por año (`data/prices/2026.csv`), el detalle de mercado por mes
> (`data/<nombre>/AAAA-MM.csv`). El bot hace commits de datos en `main` cada hora: antes de
> subir, `git pull --rebase`, y si chocas con archivos de datos, únelos sin perder filas (no
> elijas una versión entera). CI corre Python 3.11. Prueba el sitio en un navegador (claro,
> oscuro, móvil de 390 px, EN y ES) antes de subir, y confirma después que la corrida de GitHub
> terminó en verde y publicó.

## 1. Chequeo de salud

> Revisa que ontario-grid se esté actualizando bien: las últimas corridas del workflow "Update
> and publish" (cuántas por horario en los últimos días, cuántas fallaron y por qué), la fecha
> del último dato de cada dataset de `data/`, y si hay huecos (días u horas faltantes) en cada
> uno desde que empezó. Distingue huecos que todavía se pueden recuperar (IESO aún tiene el
> reporte) de los que ya no. Recupera los que se pueda y dime el resto.

## 2. Ampliar la ventana de reintentos

> Hoy cada corrida vuelve a pedir lo que falte de los últimos 7 días (`WINDOW_DAYS` en
> `ingest/update.py`), pero IESO guarda la mayoría de estos reportes ~30 días: si GitHub dejara
> de correr más de una semana quedarían huecos recuperables sin recuperar. Súbela a ~25 días
> cuidando que una corrida normal siga siendo rápida (hoy ~15 s): mide cuántas descargas extra
> provoca (por ejemplo, horas que IESO nunca publicó y se piden en cada corrida) y evítalas si
> hace falta.

## 3. Vistas para los datos que se archivan pero no se muestran

> Agrega al sitio vistas para datos que ya se archivan en `data/` y todavía no se muestran.
> Propón primero cuáles y cómo, y espera mi visto bueno: pronóstico eólico y solar de IESO
> contra lo generado (`vg_forecast/` vs `generation/`), congestión (`shadow_prices_*`: qué
> restricciones se activan y cuánto), producción por planta (`generator_output/`: salidas de
> unidades grandes, como una nuclear fuera de servicio), salidas de transmisión
> (`transmission_outages.csv`) y precios en las interconexiones (`intertie_lmp/` contra los
> zonales). Sigue el patrón del sitio: build.py arma un JSON por vista y app.js la dibuja, con
> todos los textos en EN y ES.

## 4. Guardar también el pronóstico vigente a las 9:00

> Para usar el pronóstico eólico y solar en el modelo de trading de lrg-dashboard hace falta la
> versión que existía a las 9:00 del día anterior (cuando se oferta), no solo la última antes de
> empezar el día que guarda hoy `vg_forecast/`. IESO publica ~25 versiones por día
> (`PUB_VGForecastSummary_AAAAMMDD_vN.xml`, una por hora). Agrega un dataset aparte con la versión
> vigente a las 9:00 EST de cada día para el día siguiente, y recupera todo lo que IESO todavía
> tenga.

## 5. Más reportes de IESO

> Evalúa sumar al archivo y al sitio otros reportes públicos de IESO: `DemandZonal` (demanda por
> zona, archivos anuales desde 2003), `ICIPeakTracker` (los picos de demanda que definen el
> Global Adjustment de los clientes grandes), `GlobalAdjustment` (mensual) y
> `HourlyConsumptionByFSA` (consumo horario por zona postal). Para cada uno: qué trae, cuánta
> historia hay, cuánto pesaría por año procesado a CSV y qué mostrarías. Propón antes de
> implementar.
