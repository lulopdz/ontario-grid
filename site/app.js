// Ontario Grid: loads data/*.json (built by build.py) on demand and draws each view with Plotly.
// Times are IESO market time (EST all year); every timestamp is the start of its hour.
// English by default; Spanish behind the EN/ES button (the choice is remembered).
(() => {
  const $ = (s) => document.querySelector(s);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const mean = (a) => { const x = a.filter((v) => v != null); return x.length ? x.reduce((s, v) => s + v, 0) / x.length : null; };

  // --- strings -----------------------------------------------------------------------------
  // Static text lives in index.html (English) under data-i18n keys; dynamic text is built here.
  const STRINGS = {
    en: {
      sub: "Ontario's electricity market, from IESO's public data", loading: 'Loading…',
      themeLabel: 'Toggle light/dark theme', viewsLabel: 'Views', rangeLabel: 'Range',
      tabPrices: 'Prices', tabGeneration: 'Generation', tabDemand: 'Demand', tabInterties: 'Interties',
      r7: '7 days', r30: '30 days', r90: '90 days', r365: '1 year', rAll: 'All', zone: 'Zone',
      hPrices: 'Day-ahead and real-time price', nDart: 'Positive: day-ahead cleared above real-time',
      tPrices: 'Show table (daily averages)', hMix: 'Generation mix', hGen: 'Generation by fuel',
      tGen: 'Show table (daily averages, MW)', tDemand: 'Show table (daily, MW)', hInterties: 'Net flow by neighbour',
      hAdequacy: 'Adequacy: next 7 days', tInterties: 'Show table (daily net flow, MW)',
      downloads: 'Downloads (CSV, full history):', dlPrices: 'prices', dlGeneration: 'generation', dlDemand: 'demand',
      dlInterties: 'interties', dlAdequacy: 'adequacy', code: 'Source code',
      source: 'Source: IESO public reports, refreshed about every hour. Times are IESO market time (EST, no daylight saving). Independent project, not affiliated with IESO.',
      langButton: 'ES', langLabel: 'Ver en español',
      fuels: { nuclear: 'Nuclear', gas: 'Gas', hydro: 'Hydro', wind: 'Wind', solar: 'Solar', biofuel: 'Biofuel' },
      neighbours: { quebec: 'Quebec', new_york: 'New York', michigan: 'Michigan', minnesota: 'Minnesota', manitoba: 'Manitoba' },
      lastDays: (n) => `last ${n} days`, allHistory: 'full history', hourly: 'hourly', dailyAvg: 'daily average', day: 'Day',
      updated: (b, rt) => `Updated ${b} · real-time through ${rt} EST`,
      error: "Couldn't load the data. Try reloading the page.",
      daAvg: 'Average day-ahead', rtAvg: 'Average real-time', dartAvg: 'Average DART', settledHours: 'settled hours',
      hoursPos: 'Hours with DART > 0', hours: (n) => `${n} hours`,
      pricesNote: (h, z, d) => `$/MWh, ${h}, ${z} zone. Day-ahead published through ${d}.`,
      genNote: (h) => `MW, ${h}, transmission-connected generation`,
      mixNote: (r) => `Each fuel's share of the energy generated, ${r}`,
      peak: 'Peak demand', avgDemand: 'Average demand', fcError: 'Forecast error', noForecast: 'no forecast in this range',
      fcErrorHint: (p) => `mean absolute, ${p}% of demand`, marketDemand: 'Market demand', marketHint: 'average; includes exports',
      demandTitleH: 'Ontario demand: actual and forecast',
      demandNoteH: 'MW, hourly. Forecast: the last one IESO published before each day began (available since Sep 17, 2026)',
      actual: 'Actual', forecast: 'Forecast', actualAvg: 'Actual (avg)', forecastAvg: 'Forecast (avg)', marketAvg: 'Market (avg)',
      periodPeak: 'Peak in range', daysInRange: 'Days in range', since: (d) => `since ${d}`,
      demandTitleD: 'Ontario demand: daily peak and average', demandNoteD: 'MW, daily', dailyPeak: 'Daily peak', dailyAvgDemand: 'Daily average',
      peakCol: 'Peak', avgCol: 'Average',
      netFlow: 'Total net flow', netHint: (exp, r) => `average net ${exp ? 'export' : 'import'}, ${r}`,
      topTrade: 'Largest exchange', topHint: (v, exp) => `${v} average (${exp ? 'exports' : 'imports'})`,
      minMargin: 'Lowest margin, next 7 days',
      intertiesNote: (h) => `MW, ${h}. Positive: Ontario exports; negative: imports`,
      adequacyNote: (c) => `MW, hourly. Forecast supply capacity against what is required (demand, reserves and exports). IESO forecast of ${c}`,
      supply: 'Supply capacity', required: 'Required', total: 'Total',
      tabVirtuals: 'Virtuals', hVtNet: 'Net virtual position', hVtProfile: 'Net position by hour of day',
      hVtPnl: "Virtual traders' P&L", tVirtuals: 'Show table (daily)', allHubs: 'All hubs',
      vtNetAvg: 'Average net position', vtSupplySide: 'net virtual supply (sells DA, buys back RT)',
      vtLoadSide: 'net virtual demand (buys DA, sells back RT)', vtCleared: 'Scheduled vs offered',
      vtClearedHint: (sup, dem) => `supply ${sup}% · demand ${dem}%`, vtPnl: "Virtual traders' P&L",
      vtPnlHint: (r) => `all traders together, ${r}, before fees`, vtRight: 'Hours on the right side',
      vtRightHint: (n) => `hours the net position made money, of ${n}`,
      vtNetNote: (h, z, f) => `MW, ${h}, ${z}. Positive: net virtual supply (pays when DA > RT); negative: net virtual demand. IESO publishes all traders' totals, not individual participants. Data since ${f}`,
      vtProfileNote: (r) => `Average scheduled MW by hour ending, ${r}`,
      vtPnlNote: 'Daily, $: net scheduled MW × DART, hub by hub, before fees and uplift',
      colSupOff: 'Supply offered', colSupSch: 'Supply scheduled', colDemBid: 'Demand bid', colDemSch: 'Demand scheduled',
      colNet: 'Net', colPnl: 'P&L', hourEnding: 'Hour ending',
    },
    es: {
      sub: 'El mercado eléctrico de Ontario, con los datos públicos de IESO', loading: 'Cargando…',
      themeLabel: 'Cambiar tema claro/oscuro', viewsLabel: 'Vistas', rangeLabel: 'Rango',
      tabPrices: 'Precios', tabGeneration: 'Generación', tabDemand: 'Demanda', tabInterties: 'Interconexiones',
      r7: '7 días', r30: '30 días', r90: '90 días', r365: '1 año', rAll: 'Todo', zone: 'Zona',
      hPrices: 'Precio day-ahead y real-time', nDart: 'Positivo: el day-ahead liquidó por encima del real-time',
      tPrices: 'Ver tabla (promedios diarios)', hMix: 'Mezcla de generación', hGen: 'Generación por fuente',
      tGen: 'Ver tabla (promedios diarios, MW)', tDemand: 'Ver tabla (diaria, MW)', hInterties: 'Flujo neto por vecino',
      hAdequacy: 'Adecuación: próximos 7 días', tInterties: 'Ver tabla (flujo neto diario, MW)',
      downloads: 'Descargas (CSV, historia completa):', dlPrices: 'precios', dlGeneration: 'generación', dlDemand: 'demanda',
      dlInterties: 'interconexiones', dlAdequacy: 'adecuación', code: 'Código',
      source: 'Fuente: reportes públicos de IESO, actualizados cada hora aproximadamente. Horas en hora de mercado de IESO (EST, sin horario de verano). Proyecto independiente, sin afiliación con IESO.',
      langButton: 'EN', langLabel: 'View in English',
      fuels: { nuclear: 'Nuclear', gas: 'Gas', hydro: 'Hidro', wind: 'Eólica', solar: 'Solar', biofuel: 'Biocombustible' },
      neighbours: { quebec: 'Québec', new_york: 'Nueva York', michigan: 'Michigan', minnesota: 'Minnesota', manitoba: 'Manitoba' },
      lastDays: (n) => `últimos ${n} días`, allHistory: 'toda la historia', hourly: 'por hora', dailyAvg: 'promedio diario', day: 'Día',
      updated: (b, rt) => `Actualizado ${b} · real-time hasta ${rt} EST`,
      error: 'No se pudieron cargar los datos. Prueba recargar la página.',
      daAvg: 'Day-ahead promedio', rtAvg: 'Real-time promedio', dartAvg: 'DART promedio', settledHours: 'horas liquidadas',
      hoursPos: 'Horas con DART > 0', hours: (n) => `${n} horas`,
      pricesNote: (h, z, d) => `$/MWh, ${h}, zona ${z}. Day-ahead publicado hasta el ${d}.`,
      genNote: (h) => `MW, ${h}, generación conectada a la red de transmisión`,
      mixNote: (r) => `Participación de cada fuente en la energía generada, ${r}`,
      peak: 'Demanda máxima', avgDemand: 'Demanda promedio', fcError: 'Error del pronóstico', noForecast: 'sin pronóstico en el rango',
      fcErrorHint: (p) => `promedio absoluto, ${p}% de la demanda`, marketDemand: 'Demanda de mercado', marketHint: 'promedio; incluye exportaciones',
      demandTitleH: 'Demanda de Ontario: real y pronóstico',
      demandNoteH: 'MW por hora. Pronóstico: el último publicado por IESO antes de empezar cada día (disponible desde el 17/09/2026)',
      actual: 'Real', forecast: 'Pronóstico', actualAvg: 'Real (prom.)', forecastAvg: 'Pronóstico (prom.)', marketAvg: 'Mercado (prom.)',
      periodPeak: 'Pico del período', daysInRange: 'Días en el rango', since: (d) => `desde ${d}`,
      demandTitleD: 'Demanda de Ontario: pico y promedio diario', demandNoteD: 'MW por día', dailyPeak: 'Pico diario', dailyAvgDemand: 'Promedio diario',
      peakCol: 'Pico', avgCol: 'Promedio',
      netFlow: 'Flujo neto total', netHint: (exp, r) => `${exp ? 'exportación' : 'importación'} neta promedio, ${r}`,
      topTrade: 'Mayor intercambio', topHint: (v, exp) => `${v} promedio (${exp ? 'exporta' : 'importa'})`,
      minMargin: 'Margen mínimo, próximos 7 días',
      intertiesNote: (h) => `MW, ${h}. Positivo: Ontario exporta; negativo: importa`,
      adequacyNote: (c) => `MW por hora. Capacidad de suministro pronosticada frente a lo requerido (demanda, reservas y exportaciones). Pronóstico de IESO del ${c}`,
      supply: 'Capacidad de suministro', required: 'Requerido', total: 'Total',
      tabVirtuals: 'Virtuales', hVtNet: 'Posición virtual neta', hVtProfile: 'Posición neta por hora del día',
      hVtPnl: 'P&L de los traders virtuales', tVirtuals: 'Ver tabla (diaria)', allHubs: 'Todas las zonas',
      vtNetAvg: 'Posición neta promedio', vtSupplySide: 'supply virtual neto (vende en DA, recompra en RT)',
      vtLoadSide: 'demanda virtual neta (compra en DA, revende en RT)', vtCleared: 'Programado vs ofertado',
      vtClearedHint: (sup, dem) => `supply ${sup}% · demanda ${dem}%`, vtPnl: 'P&L de los traders virtuales',
      vtPnlHint: (r) => `todos los traders juntos, ${r}, antes de cargos`, vtRight: 'Horas del lado correcto',
      vtRightHint: (n) => `horas en que la posición neta ganó, de ${n}`,
      vtNetNote: (h, z, f) => `MW, ${h}, ${z}. Positivo: supply virtual neto (gana si DA > RT); negativo: demanda virtual neta. IESO publica el total de todos los traders, no a cada participante. Datos desde el ${f}`,
      vtProfileNote: (r) => `MW programados en promedio por hora (hour ending), ${r}`,
      vtPnlNote: 'Diario, $: MW netos programados × DART, zona por zona, antes de cargos y uplift',
      colSupOff: 'Supply ofertado', colSupSch: 'Supply programado', colDemBid: 'Demanda ofertada', colDemSch: 'Demanda programada',
      colNet: 'Neto', colPnl: 'P&L', hourEnding: 'Hora (HE)',
    },
  };
  // Dates: English reads "Oct 30"; Spanish keeps day/month, since Plotly's month names are English.
  const DATES = {
    en: { tick: '%b %d', tickLong: '%b %Y', hover: '%b %d, %Y %H:%M', hoverDay: '%b %d, %Y', locale: 'en-CA' },
    es: { tick: '%d/%m', tickLong: '%m/%Y', hover: '%d/%m/%Y %H:%M', hoverDay: '%d/%m/%Y', locale: 'es-MX' },
  };

  const FUEL_KEYS = ['nuclear', 'gas', 'hydro', 'wind', 'solar', 'biofuel'];
  const NEIGHBOUR_KEYS = ['quebec', 'new_york', 'michigan', 'minnesota', 'manitoba'];
  const HOURLY_MAX_DAYS = 90; // longer ranges read the daily series (build.py keeps 120 days hourly)

  const state = { view: 'prices', days: 30, zone: 'TORONTO', vtZone: 'ALL', lang: 'en' };
  const L = () => STRINGS[state.lang] || STRINGS.en;
  const fmt = (v, d = 0) => (v == null || Number.isNaN(v) ? '—'
    : v.toLocaleString(DATES[state.lang].locale, { minimumFractionDigits: d, maximumFractionDigits: d }));
  const money = (v, d = 2) => (v == null || Number.isNaN(v) ? '—' : (v < 0 ? '−$' : '$') + fmt(Math.abs(v), d));
  const mw = (v) => fmt(v) + ' MW';

  const cache = {};
  const load = (name) => (cache[name] ||= fetch(`data/${name}.json`).then((r) => { if (!r.ok) throw new Error(name); return r.json(); }));

  function applyStrings() {
    const s = L();
    document.documentElement.lang = state.lang;
    document.querySelectorAll('[data-i18n]').forEach((el) => { if (typeof s[el.dataset.i18n] === 'string') el.textContent = s[el.dataset.i18n]; });
    document.querySelectorAll('[data-i18n-aria]').forEach((el) => el.setAttribute('aria-label', s[el.dataset.i18nAria]));
    const btn = $('#lang');
    btn.textContent = s.langButton;
    btn.setAttribute('aria-label', s.langLabel);
    btn.lang = state.lang === 'en' ? 'es' : 'en';
  }

  // --- data helpers ------------------------------------------------------------------------
  // Rows of a columnar {t: [...], col: [...]} object whose day is within `days` of the last one.
  function slice(obj, days) {
    const n = obj.t.length;
    if (!days || !n) return obj;
    const last = new Date(obj.t[n - 1].slice(0, 10) + 'T00:00:00Z');
    last.setUTCDate(last.getUTCDate() - days + 1);
    const cut = last.toISOString().slice(0, 10);
    let i = 0;
    while (i < n && obj.t[i] < cut) i++;
    const out = {};
    for (const k of Object.keys(obj)) out[k] = Array.isArray(obj[k]) ? obj[k].slice(i) : obj[k];
    return out;
  }
  // Daily means of every column (for hourly series shown over long ranges).
  function dailyMean(obj) {
    const keys = Object.keys(obj).filter((k) => k !== 't' && Array.isArray(obj[k]));
    const out = { t: [] }; keys.forEach((k) => (out[k] = []));
    let day = null, acc = {};
    const flush = () => { if (day) { out.t.push(day); keys.forEach((k) => out[k].push(mean(acc[k]))); } };
    obj.t.forEach((t, i) => {
      const d = t.slice(0, 10);
      if (d !== day) { flush(); day = d; acc = Object.fromEntries(keys.map((k) => [k, []])); }
      keys.forEach((k) => acc[k].push(obj[k][i]));
    });
    flush();
    return out;
  }

  // Daily totals of one column (null when the day has no value at all).
  function dailySum(obj, key) {
    const out = { t: [], v: [] };
    obj.t.forEach((t, i) => {
      const d = t.slice(0, 10);
      if (out.t[out.t.length - 1] !== d) { out.t.push(d); out.v.push(null); }
      if (obj[key][i] != null) out.v[out.v.length - 1] = (out.v[out.v.length - 1] || 0) + obj[key][i];
    });
    return out;
  }

  // --- chart chrome ------------------------------------------------------------------------
  const config = { responsive: true, displayModeBar: false };
  function layout(extra = {}, hourly = true) {
    const surface = css('--surface');
    const dt = DATES[state.lang];
    return {
      paper_bgcolor: surface, plot_bgcolor: surface,
      font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', size: 12, color: css('--ink-2') },
      margin: { l: 58, r: 12, t: 30, b: 36 },
      xaxis: { type: 'date', gridcolor: css('--grid'), linecolor: css('--axis'), showline: true, zeroline: false,
               tickfont: { color: css('--muted') }, tickformat: hourly ? dt.tick : dt.tickLong,
               hoverformat: hourly ? dt.hover : dt.hoverDay },
      yaxis: { gridcolor: css('--grid'), zerolinecolor: css('--axis'), tickfont: { color: css('--muted') }, separatethousands: true },
      legend: { orientation: 'h', x: 0, y: 1.02, yanchor: 'bottom', font: { color: css('--ink-2') } },
      hovermode: 'x unified',
      hoverlabel: { bgcolor: surface, bordercolor: css('--axis'), font: { color: css('--ink') } },
      separators: '.,',
      ...extra,
    };
  }
  const line = (x, y, name, color, unit) => ({
    x, y, name, type: 'scatter', mode: 'lines', line: { width: 2, color, shape: 'linear' },
    hovertemplate: `%{y:,.${unit === '$' ? 2 : 0}f}${unit === '$' ? ' $/MWh' : ' MW'}<extra>${name}</extra>`,
  });
  const draw = (id, traces, lay) => Plotly.react(id, traces, lay, config);

  function tiles(id, items) {
    $(id).innerHTML = items.map(([label, value, hint]) =>
      `<div class="tile"><div class="label">${label}</div><div class="value">${value}</div>${hint ? `<div class="hint">${hint}</div>` : ''}</div>`).join('');
  }
  function table(id, head, rows) {
    $(id).innerHTML = `<table><thead><tr>${head.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>${
      rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  }
  const lastDays = (obj, n = 14) => obj.t.map((_, i) => i).slice(-n).reverse();
  const rangeLabel = () => (state.days ? L().lastDays(state.days) : L().allHistory);
  const stamp = (t) => (t ? `${t.slice(0, 10)}, ${t.slice(11)} EST` : '');

  // --- views -------------------------------------------------------------------------------
  async function prices() {
    const s = L();
    const all = await load(`prices_${state.zone}`);
    const hourly = state.days && state.days <= HOURLY_MAX_DAYS;
    const h = slice(all, state.days);
    const d = hourly ? h : dailyMean(h);
    const dart = h.t.map((_, i) => i).filter((i) => h.rt[i] != null && h.da[i] != null).map((i) => h.dart[i]);
    tiles('#prices-tiles', [
      [s.daAvg, money(mean(h.da)), rangeLabel()],
      [s.rtAvg, money(mean(h.rt)), rangeLabel()],
      [s.dartAvg, money(mean(dart)), `${rangeLabel()}, ${s.settledHours}`],
      [s.hoursPos, dart.length ? fmt((dart.filter((v) => v > 0).length / dart.length) * 100, 0) + '%' : '—', s.hours(fmt(dart.length))],
    ]);
    $('#prices-note').textContent = s.pricesNote(hourly ? s.hourly : s.dailyAvg, state.zone, all.t[all.t.length - 1].slice(0, 10));
    draw('chart-prices', [line(d.t, d.da, 'Day-ahead', css('--s1'), '$'), line(d.t, d.rt, 'Real-time', css('--s2'), '$')], layout({}, hourly));
    const pos = css('--pos'), neg = css('--neg');
    draw('chart-dart', [{
      x: d.t, y: d.dart, type: 'bar', name: 'DART', marker: { color: d.dart.map((v) => (v >= 0 ? pos : neg)) },
      hovertemplate: '%{y:$,.2f} $/MWh<extra>DART</extra>',
    }], layout({ showlegend: false, bargap: 0.15, margin: { l: 58, r: 12, t: 8, b: 36 } }, hourly));
    const dd = dailyMean(h);
    table('#prices-table', [s.day, 'Day-ahead', 'Real-time', 'DART'],
      lastDays(dd).map((i) => [dd.t[i], money(dd.da[i]), money(dd.rt[i]), money(dd.dart[i])]));
  }

  async function generation() {
    const s = L();
    const hourly = state.days && state.days <= HOURLY_MAX_DAYS;
    const g = slice(await load(hourly ? 'generation_hourly' : 'generation_daily'), state.days);
    const colors = FUEL_KEYS.map((_, i) => css(`--s${i + 1}`));
    const names = FUEL_KEYS.map((k) => s.fuels[k]);
    const surface = css('--surface');
    draw('chart-generation', FUEL_KEYS.map((k, i) => ({
      x: g.t, y: g[k], name: names[i], type: 'scatter', mode: 'lines', stackgroup: 'gen',
      line: { width: 0.5, color: surface }, fillcolor: colors[i],
      hovertemplate: `%{y:,.0f} MW<extra>${names[i]}</extra>`,
    })), layout({ legend: { ...layout().legend, traceorder: 'normal' } }, hourly));
    $('#gen-note').textContent = s.genNote(hourly ? s.hourly : s.dailyAvg);

    // The mix over the range: one tall segmented bar, share printed where it fits.
    const totals = FUEL_KEYS.map((k) => g[k].reduce((acc, v) => acc + (v || 0), 0));
    const sum = totals.reduce((acc, v) => acc + v, 0) || 1;
    const shares = totals.map((v) => (v / sum) * 100);
    const darkLabel = !matchesDark(); // light mode's yellow takes near-black text
    $('#mix-note').textContent = s.mixNote(rangeLabel());
    $('#mix-bar').innerHTML = shares.map((share, i) => {
      if (share <= 0) return '';
      const cls = darkLabel && i === 3 ? ' class="dark-label"' : '';
      return `<div${cls} style="flex:${share} 1 0;background:${colors[i]}" title="${names[i]}: ${fmt(share, 1)}%">${share >= 7 ? `${fmt(share, 0)}%` : ''}</div>`;
    }).join('');
    $('#mix-bar').setAttribute('aria-label', names.map((n, i) => `${n} ${fmt(shares[i], 1)}%`).join(', '));
    $('#mix-legend').innerHTML = names.map((n, i) => `<li><i style="background:${colors[i]}"></i>${n} ${fmt(shares[i], 1)}%</li>`).join('');
    const gd = hourly ? dailyMean(g) : g;
    table('#generation-table', [s.day, ...names], lastDays(gd).map((i) => [gd.t[i].slice(0, 10), ...FUEL_KEYS.map((k) => fmt(gd[k][i]))]));
  }

  async function demand() {
    const s = L();
    const hourly = state.days && state.days <= HOURLY_MAX_DAYS;
    if (hourly) {
      const h = slice(await load('demand_hourly'), state.days);
      const pairs = h.t.map((_, i) => i).filter((i) => h.forecast_demand[i] != null && h.ontario_demand[i] != null);
      const mae = mean(pairs.map((i) => Math.abs(h.forecast_demand[i] - h.ontario_demand[i])));
      const avgDemand = mean(pairs.map((i) => h.ontario_demand[i]));
      const peakI = h.ontario_demand.reduce((b, v, i) => (v != null && (b < 0 || v > h.ontario_demand[b]) ? i : b), -1);
      tiles('#demand-tiles', [
        [s.peak, mw(h.ontario_demand[peakI]), stamp(h.t[peakI])],
        [s.avgDemand, mw(mean(h.ontario_demand)), rangeLabel()],
        [s.fcError, mae == null ? '—' : mw(mae), mae == null ? s.noForecast : s.fcErrorHint(fmt((mae / avgDemand) * 100, 1))],
        [s.marketDemand, mw(mean(h.market_demand)), s.marketHint],
      ]);
      $('#demand-title').textContent = s.demandTitleH;
      $('#demand-note').textContent = s.demandNoteH;
      draw('chart-demand', [line(h.t, h.ontario_demand, s.actual, css('--s1')), line(h.t, h.forecast_demand, s.forecast, css('--s2'))], layout({}, true));
      const dd = dailyMean(h);
      table('#demand-table', [s.day, s.actualAvg, s.forecastAvg, s.marketAvg],
        lastDays(dd).map((i) => [dd.t[i], fmt(dd.ontario_demand[i]), fmt(dd.forecast_demand[i]), fmt(dd.market_demand[i])]));
    } else {
      const d = slice(await load('demand_daily'), state.days);
      const peakI = d.peak.reduce((b, v, i) => (v != null && (b < 0 || v > d.peak[b]) ? i : b), -1);
      tiles('#demand-tiles', [
        [s.periodPeak, mw(d.peak[peakI]), d.t[peakI] ? d.t[peakI].slice(0, 10) : ''],
        [s.avgDemand, mw(mean(d.avg)), rangeLabel()],
        [s.daysInRange, fmt(d.t.length), s.since(d.t[0] ? d.t[0].slice(0, 10) : '—')],
      ]);
      $('#demand-title').textContent = s.demandTitleD;
      $('#demand-note').textContent = s.demandNoteD;
      draw('chart-demand', [line(d.t, d.peak, s.dailyPeak, css('--s1')), line(d.t, d.avg, s.dailyAvgDemand, css('--s2'))], layout({}, false));
      table('#demand-table', [s.day, s.peakCol, s.avgCol], lastDays(d).map((i) => [d.t[i].slice(0, 10), fmt(d.peak[i]), fmt(d.avg[i])]));
    }
  }

  async function interties() {
    const s = L();
    const hourly = state.days && state.days <= HOURLY_MAX_DAYS;
    const f = slice(await load(hourly ? 'interties_hourly' : 'interties_daily'), state.days);
    const names = NEIGHBOUR_KEYS.map((k) => s.neighbours[k]);
    const top = NEIGHBOUR_KEYS.map((k, i) => [names[i], mean(f[`${k}_flow`])])
      .sort((a, b) => Math.abs(b[1] || 0) - Math.abs(a[1] || 0))[0];
    const out = await load('adequacy_outlook');
    const minI = out.excess_capacity.reduce((b, v, i) => (v != null && (b < 0 || v < out.excess_capacity[b]) ? i : b), -1);
    const net = mean(f.total_flow);
    tiles('#interties-tiles', [
      [s.netFlow, mw(net), s.netHint(net >= 0, rangeLabel())],
      [s.topTrade, top ? top[0] : '—', top ? s.topHint(mw(top[1]), top[1] >= 0) : ''],
      [s.minMargin, minI >= 0 ? mw(out.excess_capacity[minI]) : '—', minI >= 0 ? stamp(out.t[minI]) : ''],
    ]);
    $('#interties-note').textContent = s.intertiesNote(hourly ? s.hourly : s.dailyAvg);
    draw('chart-interties', NEIGHBOUR_KEYS.map((k, i) => line(f.t, f[`${k}_flow`], names[i], css(`--s${i + 1}`))), layout({}, hourly));
    $('#adequacy-note').textContent = s.adequacyNote(out.created_at ? out.created_at.replace('T', ' ').slice(0, 16) : '—');
    draw('chart-adequacy', [line(out.t, out.supply_capacity, s.supply, css('--s1')), line(out.t, out.requirement, s.required, css('--s2'))], layout({}, true));
    const fd = hourly ? dailyMean(f) : f;
    table('#interties-table', [s.day, ...names, s.total],
      lastDays(fd).map((i) => [fd.t[i].slice(0, 10), ...NEIGHBOUR_KEYS.map((k) => fmt(fd[`${k}_flow`][i])), fmt(fd.total_flow[i])]));
  }

  async function virtuals() {
    const s = L();
    const zone = state.vtZone;
    const all = await load(`virtuals_${zone}`);
    const hourly = state.days && state.days <= HOURLY_MAX_DAYS;
    const h = slice(all, state.days);
    const d = hourly ? h : dailyMean(h);
    const zoneName = zone === 'ALL' ? s.allHubs : zone;
    const net = mean(h.net_scheduled);
    const sum = (k) => h[k].reduce((acc, v) => acc + (v || 0), 0);
    const pct = (a, b) => (b ? fmt((a / b) * 100, 0) : '—');
    // "Right side": the net position's sign against DART's, over hours with both (per hub for All).
    const sided = h.t.map((_, i) => i).filter((i) => h.pnl[i] != null && h.net_scheduled[i] !== 0);
    const right = sided.filter((i) => h.pnl[i] > 0).length;
    const pnl = sum('pnl');
    tiles('#virtuals-tiles', [
      [s.vtNetAvg, mw(net), net == null ? '' : (net >= 0 ? s.vtSupplySide : s.vtLoadSide)],
      [s.vtCleared, `${pct(sum('supply_scheduled') + sum('load_scheduled'), sum('supply_offered') + sum('load_bid'))}%`,
        s.vtClearedHint(pct(sum('supply_scheduled'), sum('supply_offered')), pct(sum('load_scheduled'), sum('load_bid')))],
      [s.vtPnl, money(pnl, 0), s.vtPnlHint(rangeLabel())],
      [s.vtRight, sided.length ? `${fmt((right / sided.length) * 100, 0)}%` : '—', s.vtRightHint(fmt(sided.length))],
    ]);
    const pos = css('--pos'), neg = css('--neg');
    const bars = (x, y, name, unit) => ({
      x, y, name, type: 'bar', marker: { color: y.map((v) => (v >= 0 ? pos : neg)) },
      hovertemplate: unit === '$' ? `%{y:$,.0f}<extra>${name}</extra>` : `%{y:,.1f} MW<extra>${name}</extra>`,
    });
    const tight = { showlegend: false, bargap: 0.15, margin: { l: 58, r: 12, t: 8, b: 36 } };
    $('#vt-net-note').textContent = s.vtNetNote(hourly ? s.hourly : s.dailyAvg, zoneName, all.t[0].slice(0, 10));
    draw('chart-vt-net', [bars(d.t, d.net_scheduled, s.colNet)], layout(tight, hourly));

    // Average net position by hour ending over the range: where in the day the crowd leans.
    const byHour = Array.from({ length: 24 }, (_, k) => mean(h.t.map((t, i) => (Number(t.slice(11, 13)) === k ? h.net_scheduled[i] : null))));
    const base = layout(tight);
    $('#vt-profile-note').textContent = s.vtProfileNote(rangeLabel());
    draw('chart-vt-profile', [bars(byHour.map((_, k) => k + 1), byHour, s.colNet)],
      { ...base, hovermode: 'closest', xaxis: { ...base.xaxis, type: 'linear', tickformat: '', hoverformat: '', dtick: window.innerWidth < 600 ? 3 : 1, title: { text: s.hourEnding, font: { size: 12 } } } });

    const daily = dailySum(h, 'pnl');
    $('#vt-pnl-note').textContent = s.vtPnlNote;
    const dayAxis = layout(tight, true);  // daily bars: day ticks ("Oct 04"), day-only hover
    draw('chart-vt-pnl', [bars(daily.t, daily.v, s.colPnl, '$')],
      { ...dayAxis, xaxis: { ...dayAxis.xaxis, hoverformat: DATES[state.lang].hoverDay } });

    const dd = dailyMean(h);
    const pnlByDay = Object.fromEntries(daily.t.map((t, i) => [t, daily.v[i]]));
    table('#virtuals-table', [s.day, s.colSupOff, s.colSupSch, s.colDemBid, s.colDemSch, s.colNet, s.colPnl],
      lastDays(dd).map((i) => [dd.t[i], fmt(dd.supply_offered[i], 1), fmt(dd.supply_scheduled[i], 1), fmt(dd.load_bid[i], 1),
        fmt(dd.load_scheduled[i], 1), fmt(dd.net_scheduled[i], 1), money(pnlByDay[dd.t[i]], 0)]));
  }

  const VIEWS = { prices, generation, demand, interties, virtuals };

  // --- wiring ------------------------------------------------------------------------------
  let meta = null;
  function matchesDark() {
    const t = document.documentElement.dataset.theme;
    return t ? t === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  async function render() {
    applyStrings();
    if (meta) $('#updated').textContent = L().updated(meta.built_at, meta.prices_last_rt);
    document.querySelectorAll('.view').forEach((sec) => (sec.hidden = sec.id !== `view-${state.view}`));
    document.querySelectorAll('.tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.view === state.view)));
    document.querySelectorAll('#range button').forEach((b) => b.classList.toggle('on', Number(b.dataset.days) === state.days));
    // Prices and Virtuals share the zone picker, each with its own list and choice.
    $('#zone-wrap').hidden = !['prices', 'virtuals'].includes(state.view);
    if (meta && ['prices', 'virtuals'].includes(state.view)) {
      const vt = state.view === 'virtuals';
      const zones = vt ? meta.virtual_zones : meta.zones;
      const key = vt ? 'vtZone' : 'zone';
      if (!zones.includes(state[key])) state[key] = zones[0];
      $('#zone').innerHTML = zones.map((z) => `<option value="${z}" ${z === state[key] ? 'selected' : ''}>${z === 'ALL' ? L().allHubs : z}</option>`).join('');
    }
    document.querySelectorAll('.load-error').forEach((el) => el.remove());
    try {
      await VIEWS[state.view]();
    } catch (e) {
      console.error(e);
      $(`#view-${state.view}`).insertAdjacentHTML('afterbegin', `<p class="card load-error">${L().error}</p>`);
    }
  }
  function save() {
    try { localStorage.setItem('ontario-grid', JSON.stringify(state)); } catch (e) { /* storage unavailable */ }
  }

  async function init() {
    try { Object.assign(state, JSON.parse(localStorage.getItem('ontario-grid') || '{}')); } catch (e) { /* ignore */ }
    if (!STRINGS[state.lang]) state.lang = 'en';
    try { const t = localStorage.getItem('ontario-grid-theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* ignore */ }
    applyStrings();
    meta = await load('meta');
    if (!meta.zones.includes(state.zone)) state.zone = meta.zones.includes('TORONTO') ? 'TORONTO' : meta.zones[0];
    document.querySelectorAll('.tabs button').forEach((b) => b.addEventListener('click', () => { state.view = b.dataset.view; save(); render(); }));
    document.querySelectorAll('#range button').forEach((b) => b.addEventListener('click', () => { state.days = Number(b.dataset.days); save(); render(); }));
    $('#zone').addEventListener('change', (e) => { state[state.view === 'virtuals' ? 'vtZone' : 'zone'] = e.target.value; save(); render(); });
    $('#lang').addEventListener('click', () => { state.lang = state.lang === 'en' ? 'es' : 'en'; save(); render(); });
    $('#theme').addEventListener('click', () => {
      const next = matchesDark() ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem('ontario-grid-theme', next); } catch (e) { /* ignore */ }
      render();
    });
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', render);
    render();
  }
  init();
})();
