// Ontario Grid: loads data/*.json (built by build.py) on demand and draws each view with Plotly.
// Times are IESO market time (EST all year); every timestamp is the start of its hour.
(() => {
  const $ = (s) => document.querySelector(s);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const fmt = (v, d = 0) => (v == null || Number.isNaN(v) ? '—' : v.toLocaleString('es-MX', { minimumFractionDigits: d, maximumFractionDigits: d }));
  const money = (v, d = 2) => (v == null || Number.isNaN(v) ? '—' : (v < 0 ? '−$' : '$') + fmt(Math.abs(v), d));
  const mw = (v) => fmt(v) + ' MW';
  const mean = (a) => { const x = a.filter((v) => v != null); return x.length ? x.reduce((s, v) => s + v, 0) / x.length : null; };

  const FUELS = [['nuclear', 'Nuclear'], ['gas', 'Gas'], ['hydro', 'Hidro'], ['wind', 'Eólica'], ['solar', 'Solar'], ['biofuel', 'Biocombustible']];
  const NEIGHBOURS = [['quebec', 'Québec'], ['new_york', 'Nueva York'], ['michigan', 'Michigan'], ['minnesota', 'Minnesota'], ['manitoba', 'Manitoba']];
  const HOURLY_MAX_DAYS = 90; // longer ranges read the daily series (build.py keeps 120 days hourly)

  const state = { view: 'prices', days: 30, zone: 'TORONTO' };
  const cache = {};
  const load = (name) => (cache[name] ||= fetch(`data/${name}.json`).then((r) => { if (!r.ok) throw new Error(name); return r.json(); }));

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

  // --- chart chrome ------------------------------------------------------------------------
  const config = { responsive: true, displayModeBar: false };
  function layout(extra = {}, hourly = true) {
    const surface = css('--surface');
    return {
      paper_bgcolor: surface, plot_bgcolor: surface,
      font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', size: 12, color: css('--ink-2') },
      margin: { l: 58, r: 12, t: 30, b: 36 },
      xaxis: { type: 'date', gridcolor: css('--grid'), linecolor: css('--axis'), showline: true, zeroline: false,
               tickfont: { color: css('--muted') }, tickformat: hourly ? '%d/%m' : '%m/%Y',
               hoverformat: hourly ? '%d/%m/%Y %H:%M' : '%d/%m/%Y' },
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
  const rangeLabel = () => (state.days ? `últimos ${state.days} días` : 'toda la historia');

  // --- views -------------------------------------------------------------------------------
  async function prices() {
    const all = await load(`prices_${state.zone}`);
    const hourly = state.days && state.days <= HOURLY_MAX_DAYS;
    const h = slice(all, state.days);
    const d = hourly ? h : dailyMean(h);
    const withRt = h.rt.map((v, i) => (v == null || h.da[i] == null ? null : i)).filter((i) => i != null);
    const dart = withRt.map((i) => h.dart[i]);
    const lastDa = all.t[all.t.length - 1].slice(0, 10);
    tiles('#prices-tiles', [
      ['Day-ahead promedio', money(mean(h.da)), rangeLabel()],
      ['Real-time promedio', money(mean(h.rt)), rangeLabel()],
      ['DART promedio', money(mean(dart)), `${rangeLabel()}, horas liquidadas`],
      ['Horas con DART > 0', dart.length ? fmt((dart.filter((v) => v > 0).length / dart.length) * 100, 0) + '%' : '—', `${fmt(dart.length)} horas`],
    ]);
    $('#prices-note').textContent = `$/MWh, ${hourly ? 'por hora' : 'promedio diario'}, zona ${state.zone}. Day-ahead publicado hasta el ${lastDa}.`;
    draw('chart-prices', [line(d.t, d.da, 'Day-ahead', css('--s1'), '$'), line(d.t, d.rt, 'Real-time', css('--s2'), '$')],
      layout({}, hourly));
    const pos = css('--pos'), neg = css('--neg');
    draw('chart-dart', [{
      x: d.t, y: d.dart, type: 'bar', name: 'DART', marker: { color: d.dart.map((v) => (v >= 0 ? pos : neg)) },
      hovertemplate: '%{y:$,.2f} $/MWh<extra>DART</extra>',
    }], layout({ showlegend: false, bargap: 0.15, margin: { l: 58, r: 12, t: 8, b: 36 } }, hourly));
    const dd = dailyMean(h);
    table('#prices-table', ['Día', 'Day-ahead', 'Real-time', 'DART'],
      lastDays(dd).map((i) => [dd.t[i], money(dd.da[i]), money(dd.rt[i]), money(dd.dart[i])]));
  }

  async function generation() {
    const hourly = state.days && state.days <= HOURLY_MAX_DAYS;
    const src = await load(hourly ? 'generation_hourly' : 'generation_daily');
    const g = slice(src, state.days);
    const colors = FUELS.map((_, i) => css(`--s${i + 1}`));
    const surface = css('--surface');
    draw('chart-generation', FUELS.map(([k, label], i) => ({
      x: g.t, y: g[k], name: label, type: 'scatter', mode: 'lines', stackgroup: 'gen',
      line: { width: 0.5, color: surface }, fillcolor: colors[i],
      hovertemplate: `%{y:,.0f} MW<extra>${label}</extra>`,
    })), layout({ legend: { ...layout().legend, traceorder: 'normal' } }, hourly));
    $('#gen-note').textContent = `MW, ${hourly ? 'por hora' : 'promedio diario'}, generación conectada a la red de transmisión`;

    // The mix over the range: one tall segmented bar, share printed where it fits.
    const totals = FUELS.map(([k]) => g[k].reduce((s, v) => s + (v || 0), 0));
    const sum = totals.reduce((s, v) => s + v, 0) || 1;
    const darkLabel = !matchesDark();
    $('#mix-note').textContent = `Participación de cada fuente en la energía generada, ${rangeLabel()}`;
    $('#mix-bar').innerHTML = FUELS.map(([, label], i) => {
      const share = (totals[i] / sum) * 100;
      if (share <= 0) return '';
      const txt = share >= 7 ? `${fmt(share, 0)}%` : '';
      const cls = darkLabel && i === 3 ? ' class="dark-label"' : '';
      return `<div${cls} style="flex:${share} 1 0;background:${colors[i]}" title="${label}: ${fmt(share, 1)}%">${txt}</div>`;
    }).join('');
    $('#mix-bar').setAttribute('aria-label', FUELS.map(([, l], i) => `${l} ${fmt((totals[i] / sum) * 100, 1)}%`).join(', '));
    $('#mix-legend').innerHTML = FUELS.map(([, l], i) => `<li><i style="background:${colors[i]}"></i>${l} ${fmt((totals[i] / sum) * 100, 1)}%</li>`).join('');
    const gd = hourly ? dailyMean(g) : g;
    table('#generation-table', ['Día', ...FUELS.map(([, l]) => l)], lastDays(gd).map((i) => [gd.t[i].slice(0, 10), ...FUELS.map(([k]) => fmt(gd[k][i]))]));
  }

  async function demand() {
    const hourly = state.days && state.days <= HOURLY_MAX_DAYS;
    if (hourly) {
      const h = slice(await load('demand_hourly'), state.days);
      const pairs = h.t.map((_, i) => i).filter((i) => h.forecast_demand[i] != null && h.ontario_demand[i] != null);
      const mae = mean(pairs.map((i) => Math.abs(h.forecast_demand[i] - h.ontario_demand[i])));
      const avgDemand = mean(pairs.map((i) => h.ontario_demand[i]));
      const peakI = h.ontario_demand.reduce((b, v, i) => (v != null && (b < 0 || v > h.ontario_demand[b]) ? i : b), -1);
      tiles('#demand-tiles', [
        ['Demanda máxima', mw(h.ontario_demand[peakI]), h.t[peakI] ? `${h.t[peakI].slice(0, 10)}, ${h.t[peakI].slice(11)} EST` : ''],
        ['Demanda promedio', mw(mean(h.ontario_demand)), rangeLabel()],
        ['Error del pronóstico', mae == null ? '—' : mw(mae), mae == null ? 'sin pronóstico en el rango' : `promedio absoluto, ${fmt((mae / avgDemand) * 100, 1)}% de la demanda`],
        ['Demanda de mercado', mw(mean(h.market_demand)), 'promedio; incluye exportaciones'],
      ]);
      $('#demand-title').textContent = 'Demanda de Ontario: real y pronóstico';
      $('#demand-note').textContent = 'MW por hora. Pronóstico: el último publicado por IESO antes de empezar cada día (disponible desde el 17/09/2026)';
      draw('chart-demand', [line(h.t, h.ontario_demand, 'Real', css('--s1')), line(h.t, h.forecast_demand, 'Pronóstico', css('--s2'))], layout({}, true));
      const dd = dailyMean(h);
      table('#demand-table', ['Día', 'Real (prom.)', 'Pronóstico (prom.)', 'Mercado (prom.)'],
        lastDays(dd).map((i) => [dd.t[i], fmt(dd.ontario_demand[i]), fmt(dd.forecast_demand[i]), fmt(dd.market_demand[i])]));
    } else {
      const d = slice(await load('demand_daily'), state.days);
      const peakI = d.peak.reduce((b, v, i) => (v != null && (b < 0 || v > d.peak[b]) ? i : b), -1);
      tiles('#demand-tiles', [
        ['Pico del período', mw(d.peak[peakI]), d.t[peakI] ? d.t[peakI].slice(0, 10) : ''],
        ['Demanda promedio', mw(mean(d.avg)), rangeLabel()],
        ['Días en el rango', fmt(d.t.length), `desde ${d.t[0] ? d.t[0].slice(0, 10) : '—'}`],
      ]);
      $('#demand-title').textContent = 'Demanda de Ontario: pico y promedio diario';
      $('#demand-note').textContent = 'MW por día';
      draw('chart-demand', [line(d.t, d.peak, 'Pico diario', css('--s1')), line(d.t, d.avg, 'Promedio diario', css('--s2'))], layout({}, false));
      table('#demand-table', ['Día', 'Pico', 'Promedio'], lastDays(d).map((i) => [d.t[i].slice(0, 10), fmt(d.peak[i]), fmt(d.avg[i])]));
    }
  }

  async function interties() {
    const hourly = state.days && state.days <= HOURLY_MAX_DAYS;
    const f = slice(await load(hourly ? 'interties_hourly' : 'interties_daily'), state.days);
    const means = NEIGHBOURS.map(([k, l]) => [l, mean(f[`${k}_flow`])]);
    const top = means.slice().sort((a, b) => Math.abs(b[1] || 0) - Math.abs(a[1] || 0))[0];
    const out = await load('adequacy_outlook');
    const minI = out.excess_capacity.reduce((b, v, i) => (v != null && (b < 0 || v < out.excess_capacity[b]) ? i : b), -1);
    const net = mean(f.total_flow);
    tiles('#interties-tiles', [
      ['Flujo neto total', mw(net), `${net >= 0 ? 'exportación' : 'importación'} neta promedio, ${rangeLabel()}`],
      ['Mayor intercambio', top ? top[0] : '—', top ? `${mw(top[1])} promedio (${top[1] >= 0 ? 'exporta' : 'importa'})` : ''],
      ['Margen mínimo, próximos 7 días', minI >= 0 ? mw(out.excess_capacity[minI]) : '—', minI >= 0 ? `${out.t[minI].slice(0, 10)}, ${out.t[minI].slice(11)} EST` : ''],
    ]);
    $('#interties-note').textContent = `MW, ${hourly ? 'por hora' : 'promedio diario'}. Positivo: Ontario exporta; negativo: importa`;
    draw('chart-interties', NEIGHBOURS.map(([k, l], i) => line(f.t, f[`${k}_flow`], l, css(`--s${i + 1}`))), layout({}, hourly));
    $('#adequacy-note').textContent = `MW por hora. Capacidad de suministro pronosticada frente a lo requerido (demanda, reservas y exportaciones). Pronóstico de IESO del ${out.created_at ? out.created_at.replace('T', ' ').slice(0, 16) : '—'}`;
    draw('chart-adequacy', [line(out.t, out.supply_capacity, 'Capacidad de suministro', css('--s1')), line(out.t, out.requirement, 'Requerido', css('--s2'))], layout({}, true));
    const fd = hourly ? dailyMean(f) : f;
    table('#interties-table', ['Día', ...NEIGHBOURS.map(([, l]) => l), 'Total'],
      lastDays(fd).map((i) => [fd.t[i].slice(0, 10), ...NEIGHBOURS.map(([k]) => fmt(fd[`${k}_flow`][i])), fmt(fd.total_flow[i])]));
  }

  const VIEWS = { prices, generation, demand, interties };

  // --- wiring ------------------------------------------------------------------------------
  function matchesDark() {
    const t = document.documentElement.dataset.theme;
    return t ? t === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  async function render() {
    document.querySelectorAll('.view').forEach((s) => (s.hidden = s.id !== `view-${state.view}`));
    document.querySelectorAll('.tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.view === state.view)));
    document.querySelectorAll('#range button').forEach((b) => b.classList.toggle('on', Number(b.dataset.days) === state.days));
    $('#zone-wrap').hidden = state.view !== 'prices';
    try {
      await VIEWS[state.view]();
    } catch (e) {
      console.error(e);
      $(`#view-${state.view}`).insertAdjacentHTML('afterbegin', '<p class="card">No se pudieron cargar los datos. Prueba recargar la página.</p>');
    }
  }
  function save() {
    try { localStorage.setItem('ontario-grid', JSON.stringify(state)); } catch (e) { /* storage unavailable */ }
  }

  async function init() {
    try { Object.assign(state, JSON.parse(localStorage.getItem('ontario-grid') || '{}')); } catch (e) { /* ignore */ }
    try { const t = localStorage.getItem('ontario-grid-theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* ignore */ }
    const meta = await load('meta');
    $('#zone').innerHTML = meta.zones.map((z) => `<option ${z === state.zone ? 'selected' : ''}>${z}</option>`).join('');
    if (!meta.zones.includes(state.zone)) state.zone = meta.zones[0];
    $('#updated').textContent = `Actualizado ${meta.built_at} · real-time hasta ${meta.prices_last_rt} EST`;
    document.querySelectorAll('.tabs button').forEach((b) => b.addEventListener('click', () => { state.view = b.dataset.view; save(); render(); }));
    document.querySelectorAll('#range button').forEach((b) => b.addEventListener('click', () => { state.days = Number(b.dataset.days); save(); render(); }));
    $('#zone').addEventListener('change', (e) => { state.zone = e.target.value; save(); render(); });
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
