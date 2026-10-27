(function () {
  "use strict";
  const S = window.PEIScore;
  const ROWS = S.expand(PEI);
  const Y0 = 1950, Y1 = 2025;
  const META = PEI.countries;
  const CODES = Object.keys(META).sort((a, b) => META[a].name.localeCompare(META[b].name));
  const PANEL_A = CODES.filter((c) => META[c].panelA), PANEL_B = CODES.filter((c) => META[c].panelB);
  const D = PEI.defaults;
  const DEF = { w: { p1: D.w.p1_throughput, p2: D.w.p2_fiscal, p3: D.w.p3_stability, p4: D.w.p4_implementation },
                snap: D.snap, pm: D.pm, grace: D.grace, decree: D.decree };
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const MEAS = { pei: "Index", p1: "Laws passed", p2: "Budget on time", p3: "Government stability", rank: "Ranking" };
  const MEAS_SHORT = { pei: "index", p1: "laws pillar", p2: "budget pillar", p3: "stability pillar", rank: "ranking" };
  const isR = () => state.m === "rank";
  const NC = 31;
  const cmpV = (a, b) => (a.v === null || a.v === undefined ? 1 : b.v === null || b.v === undefined ? -1 : isR() ? a.v - b.v : b.v - a.v);
  const toScore = (v) => (isR() ? (100 * (NC - v)) / (NC - 1) : v);
  const SERIES_COL = ["--c1", "--c2", "--c3", "--c4", "--c5", "--c6", "--c7", "--c8", "--c9", "--c10"];
  const col = (i) => SERIES_COL[i % SERIES_COL.length];
  const GROUPS = [
    { k: "big5", name: "Big five", desc: "Germany, UK, France, Italy, Spain", the: "the big five", c: ["DE", "UK", "FR", "IT", "ES"] },
    { k: "benelux", name: "Benelux", desc: "Belgium, Netherlands, Luxembourg", the: "Benelux", c: ["BE", "NL", "LU"] },
    { k: "nordic", name: "Nordics", desc: "Denmark, Finland, Iceland, Norway, Sweden", the: "the Nordics", c: ["DK", "FI", "IS", "NO", "SE"] },
    { k: "south", name: "Southern Europe", desc: "Spain, Italy, Greece, Portugal", the: "Southern Europe", c: ["ES", "IT", "GR", "PT"] },
    { k: "east", name: "Eastern Europe", desc: "Poland, Slovakia, Hungary, Slovenia, Croatia, Romania, Bulgaria, the Baltics", the: "Eastern Europe", c: ["PL", "SK", "HU", "SI", "HR", "RO", "BG", "EE", "LV", "LT"] },
    { k: "yugo", name: "Former Yugoslavia", desc: "Slovenia, Croatia", the: "former Yugoslavia", c: ["SI", "HR"] },
  ];
  const GROUP = Object.fromEntries(GROUPS.map((g) => [g.k, g]));
  const state = { sel: [], from: 1950, to: 2025, m: "pei", base: "all", tab: "heat", P: clone(DEF) };

  // ---- data index ----
  const RAW = {}; // RAW[c][y-Y0] = row
  for (const c of CODES) RAW[c] = new Array(Y1 - Y0 + 1).fill(null);
  for (const r of ROWS) if (r.y >= Y0 && r.y <= Y1) RAW[r.c][r.y - Y0] = r;
  const CABS = PEI.cabinets.map((a) => Object.fromEntries(PEI.cabCols.map((k, i) => [k, a[i]])));
  const NOTES = (PEI.annotations || []).filter((a) => a && META[a.country] && a.year >= Y0 && a.year <= Y1);
  let SC = {};
  function rescore() {
    SC = {};
    for (const c of CODES) SC[c] = RAW[c].map((r) => (r ? S.scoreRow(r, state.P) : { p1: null, p2: null, p3: null, pei: null }));
    for (let i = 0; i <= Y1 - Y0; i++) {
      const xs = CODES.filter((c) => SC[c][i].pei !== null).sort((a, b) => SC[b][i].pei - SC[a][i].pei);
      CODES.forEach((c) => { SC[c][i].rank = null; SC[c][i].rankN = xs.length; });
      xs.forEach((c, k) => { SC[c][i].rank = k + 1; });
    }
  }
  const val = (c, y, m = state.m) => { const s = SC[c][y - Y0]; return s ? s[m] : null; };
  const years = () => d3.range(state.from, state.to + 1);
  const single = () => state.from === state.to;
  const vFrom = () => (single() ? Math.max(Y0, state.from - 10) : state.from);
  const vTo = () => (single() ? Math.min(Y1, state.to + 10) : state.to);
  const viewYears = () => d3.range(vFrom(), vTo() + 1);
  const winLbl = () => (single() ? String(state.from) : `${state.from}–${state.to}`);
  const inWin = (y) => y >= state.from && y <= state.to;
  const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
  const baseSet = () => (GROUP[state.base] ? GROUP[state.base].c : state.base === "A" ? PANEL_A : state.base === "B" ? PANEL_B : CODES);
  function avgSeries(m = state.m) {
    const set = baseSet();
    return viewYears().map((y) => {
      const v = set.map((c) => val(c, y, m)).filter((x) => x !== null).sort(d3.ascending);
      return { y, v: v.length ? mean(v) : null, q1: v.length >= 4 ? d3.quantileSorted(v, 0.25) : null,
               q3: v.length >= 4 ? d3.quantileSorted(v, 0.75) : null, n: v.length };
    });
  }
  function winAvg(c, from = state.from, to = state.to, m = state.m) {
    const v = d3.range(from, to + 1).map((y) => val(c, y, m)).filter((x) => x !== null);
    return { v: v.length ? mean(v) : null, n: v.length };
  }
  function ranking(from = state.from, to = state.to) {
    const minYears = Math.max(1, Math.ceil((to - from + 1) / 3));
    return CODES.map((c) => ({ c, ...winAvg(c, from, to) })).filter((d) => d.v !== null && d.n >= minYears).sort(cmpV);
  }
  const ord = (n) => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th");
  const f1 = (v) => (v === null || v === undefined ? "–" : isR() && Number.isInteger(v) ? String(v) : v.toFixed(1));
  const sgn = (v) => (v === null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1));
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const el = (id) => document.getElementById(id);
  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const k in attrs || {}) {
      if (k === "class") e.className = attrs[k]; else if (k === "text") e.textContent = attrs[k];
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), attrs[k]); else e.setAttribute(k, attrs[k]);
    }
    for (const k of kids) if (k !== null && k !== undefined) e.append(k);
    return e;
  }
  function coverage(c) {
    const first = (f) => { const r = ROWS.find((r) => r.c === c && !r.pre && f(r)); return r ? r.y : null; };
    return { laws: first((r) => r.p1b !== null), budget: first((r) => r.inf !== null), structural: ROWS.some((r) => r.c === c && r.reg === "structural_na"),
             govt: first((r) => r.care !== null), scored: META[c].from };
  }
  const COV = Object.fromEntries(CODES.map((c) => [c, coverage(c)]));
  function covLine(c) {
    const v = COV[c], parts = [`scored from ${Math.max(v.scored, Y0)}`];
    parts.push(v.laws ? `laws from ${v.laws}` : "no law data");
    parts.push(v.structural ? "budget not scored (no single on-time test)" : v.budget ? `budgets from ${v.budget}` : "no budget data");
    parts.push(v.govt ? `governments from ${v.govt}` : "no government data");
    return `${META[c].name}: ${parts.join(", ")}.`;
  }

  // ---- color scale ----
  let scale;
  function makeScale() {
    scale = d3.scaleLinear().domain([0, 25, 50, 75, 100]).range(["--s0", "--s1", "--s2", "--s3", "--s4"].map(css)).interpolate(d3.interpolateLab).clamp(true);
  }

  // ---- tooltip ----
  const tip = el("tip");
  function showTip(evt, nodes) {
    tip.replaceChildren(...nodes);
    tip.hidden = false;
    const pad = 12, w = tip.offsetWidth, hgt = tip.offsetHeight;
    let x = evt.clientX + 14, y = evt.clientY + 14;
    if (x + w + pad > window.innerWidth) x = evt.clientX - w - 14;
    if (y + hgt + pad > window.innerHeight) y = evt.clientY - hgt - 14;
    tip.style.left = Math.max(pad, x) + "px"; tip.style.top = Math.max(pad, y) + "px";
  }
  const hideTip = () => { tip.hidden = true; };
  const tipRow = (label, value, color) => h("div", { class: "r" }, h("span", {}, color ? h("i", { style: `background:${color}` }) : null, label), h("span", { text: value }));

  // ---- line chart ----
  function lineChart(box, opt) {
    box.replaceChildren();
    const R = isR() && !opt.scoreScale;
    const W = Math.max(280, box.clientWidth), H = opt.height || (W < 560 ? 240 : 320);
    const m = { t: 14, r: 14, b: 26, l: 32 };
    const svg = d3.select(box).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("width", "100%").attr("role", "img").attr("aria-label", opt.label || "Line chart");
    const x = d3.scaleLinear().domain([vFrom(), Math.max(vTo(), vFrom() + 1)]).range([m.l, W - m.r]);
    if (single()) svg.append("rect").attr("x", x(state.from - 0.5)).attr("width", x(state.from + 0.5) - x(state.from - 0.5)).attr("y", m.t).attr("height", H - m.t - m.b).style("fill", "var(--accent-soft)");
    const y = d3.scaleLinear().domain(R ? [NC, 1] : [0, 100]).range([H - m.b, m.t]);
    svg.append("g").selectAll("line").data(R ? [1, 8, 16, 24, 31] : [0, 25, 50, 75, 100]).join("line").attr("class", "gridline")
      .attr("x1", m.l).attr("x2", W - m.r).attr("y1", (d) => y(d)).attr("y2", (d) => y(d));
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - m.b})`)
      .call(d3.axisBottom(x).ticks(Math.min(10, Math.floor(W / 70), vTo() - vFrom())).tickFormat(d3.format("d")).tickSizeOuter(0)).select(".domain").remove();
    svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).tickValues(R ? [1, 10, 20, 31] : [0, 50, 100]).tickSize(0).tickPadding(6)).select(".domain").remove();
    (opt.eras || []).forEach((e) => {
      if (e.y <= vFrom() || e.y > vTo()) return;
      svg.append("line").attr("x1", x(e.y - 0.5)).attr("x2", x(e.y - 0.5)).attr("y1", m.t).attr("y2", H - m.b).style("stroke", "var(--ink-3)").attr("stroke-dasharray", "2 3");
      svg.append("text").attr("x", x(e.y - 0.5) + 4).attr("y", m.t + 10).text(e.label).style("fill", "var(--ink-3)").style("font-size", "11px");
    });
    if (opt.avg) {
      const band = opt.avg.filter((d) => d.q1 !== null);
      svg.append("path").datum(opt.avg).style("fill", "var(--band)")
        .attr("d", d3.area().defined((d) => d.q1 !== null).x((d) => x(d.y)).y0((d) => y(d.q1)).y1((d) => y(d.q3)));
      svg.append("path").datum(opt.avg).style("fill", "none").style("stroke", "var(--avg)").style("stroke-width", 2).attr("stroke-dasharray", opt.series.length ? "5 4" : null)
        .attr("d", d3.line().defined((d) => d.v !== null).x((d) => x(d.y)).y((d) => y(d.v)));
      void band;
    }
    for (const s of opt.series) {
      const ln = d3.line().defined((d) => d.v !== null).x((d) => x(d.y)).y((d) => y(d.v));
      svg.append("path").datum(s.values).style("fill", "none").style("stroke", `var(${s.color})`).style("stroke-width", s.width || 2.2).style("stroke-linejoin", "round").attr("d", ln);
      const iso = s.values.filter((d, i, a) => d.v !== null && (i === 0 || a[i - 1].v === null) && (i === a.length - 1 || a[i + 1].v === null));
      svg.append("g").selectAll("circle").data(iso).join("circle").attr("cx", (d) => x(d.y)).attr("cy", (d) => y(d.v)).attr("r", 2.5).style("fill", `var(${s.color})`);
    }
    (opt.notes || []).forEach((n, i) => {
      const v = opt.series[0].values.find((d) => d.y === n.year);
      if (!v || v.v === null) return;
      const g = svg.append("g").attr("transform", `translate(${x(n.year)},${y(v.v)})`).attr("tabindex", 0).style("cursor", "help");
      g.append("circle").attr("r", 8).style("fill", "var(--ink)").style("stroke", "var(--surface)").style("stroke-width", 2);
      g.append("text").text(i + 1).attr("text-anchor", "middle").attr("dy", "0.35em").style("fill", "var(--bg)").style("font-size", "10px").style("font-weight", 700);
      const show = (e) => showTip(e, [h("div", { class: "tt", text: `${n.year} · ${n.label}` }), h("div", { text: n.text || "" })]);
      g.on("pointerenter", show).on("pointermove", show).on("pointerleave", hideTip)
        .on("focus", (e) => { const b = e.target.getBoundingClientRect(); show({ clientX: b.right, clientY: b.bottom }); }).on("blur", hideTip);
    });
    // crosshair
    const cross = svg.append("line").attr("y1", m.t).attr("y2", H - m.b).style("stroke", "var(--ink-3)").style("opacity", 0);
    svg.append("rect").attr("x", m.l).attr("y", m.t).attr("width", W - m.l - m.r).attr("height", H - m.t - m.b).style("fill", "transparent").lower()
      .on("pointermove", (e) => {
        const [px] = d3.pointer(e); const yr = Math.round(x.invert(px));
        if (yr < vFrom() || yr > vTo()) return;
        cross.attr("x1", x(yr)).attr("x2", x(yr)).style("opacity", 0.5);
        const nodes = [h("div", { class: "tt", text: String(yr) })];
        for (const s of opt.series) { const d = s.values.find((q) => q.y === yr); nodes.push(tipRow(s.label, d && d.v !== null ? f1(d.v) : "no data", `var(${s.color})`)); }
        if (opt.avg) { const a = opt.avg.find((q) => q.y === yr); if (a) { nodes.push(tipRow(`Average (${a.n})`, f1(a.v), "var(--avg)")); if (a.q1 !== null) nodes.push(tipRow("Middle half", `${f1(a.q1)}–${f1(a.q3)}`)); } }
        showTip(e, nodes);
      })
      .on("pointerleave", () => { cross.style("opacity", 0); hideTip(); });
    svg.select("rect").raise();
    svg.selectAll("g[tabindex]").raise();
  }

  // ---- controls ----
  function buildControls() {
    buildMenu();
    el("base-groups").replaceChildren(...GROUPS.map((g) => h("option", { value: g.k, text: `${g.name} (${g.c.length})` })));
    el("btn-all").addEventListener("click", () => { state.sel = []; render(); });
    const from = el("from"), to = el("to");
    const onRange = (which) => {
      let a = +from.value, b = +to.value;
      if (a > b) { if (which === "from") a = b; else b = a; }
      state.from = a; state.to = b; from.value = a; to.value = b; render();
    };
    from.addEventListener("input", () => onRange("from")); to.addEventListener("input", () => onRange("to"));
    const one = el("oneyear");
    const setOne = () => { const v = Math.round(+one.value); if (!one.value || v < Y0 || v > Y1) return; state.from = state.to = v; from.value = to.value = v; render(); };
    one.addEventListener("change", setOne);
    one.addEventListener("keydown", (e) => { if (e.key === "Enter") setOne(); });
    document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
      const p = b.dataset.preset; state.to = Y1; state.from = p === "last10" ? Y1 - 9 : +p; from.value = state.from; to.value = state.to; el("oneyear").value = ""; render();
    }));
    document.querySelectorAll("#measure button").forEach((b) => b.addEventListener("click", () => { state.m = b.dataset.m; render(); }));
    el("base").addEventListener("change", (e) => { state.base = e.target.value; render(); });
    document.querySelectorAll("#alltabs button").forEach((b) => b.addEventListener("click", () => { state.tab = b.dataset.t; render(); }));
    el("reset").addEventListener("click", () => { state.P = clone(DEF); buildRecipe(); rescore(); render(); });
    buildRecipe();
  }
  const PILLARS = [
    { k: "p1", name: "Laws passed", d: "Substantive laws, against the country's own record" },
    { k: "p2", name: "Budget on time", d: "Budget in force on day one of the fiscal year" },
    { k: "p3", name: "Government stability", d: "Full-power government, no snap election or PM change" },
  ];
  const ADV = [
    { k: "snap", name: "Snap election penalty", unit: "points", min: 0, max: 40, step: 1, d: "Taken off stability in a year with an early election" },
    { k: "pm", name: "PM change penalty", unit: "points", min: 0, max: 30, step: 1, d: "Per change of prime minister in the year, up to two" },
    { k: "grace", name: "Late-budget grace", unit: "days", min: 0, max: 180, step: 5, d: "A budget this late still scores 50" },
    { k: "decree", name: "Decree penalty", unit: "points", min: 0, max: 100, step: 5, d: "× share of laws made by government decree" },
  ];
  let raf = 0;
  const schedule = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => { rescore(); render(); }); };
  function buildRecipe() {
    const box = el("pillars"); box.replaceChildren();
    for (const p of PILLARS) {
      const inp = h("input", { type: "range", min: 0, max: 100, step: 1, value: state.P.w[p.k], id: "w-" + p.k, "aria-label": `${p.name} weight` });
      if (p.off) inp.disabled = true;
      inp.addEventListener("input", () => { state.P.w[p.k] = +inp.value; schedule(); });
      box.append(h("div", { class: "pill" + (p.off ? " off" : "") },
        h("div", { class: "row" }, h("span", { class: "nm", text: p.name }), h("span", { class: "sh", id: "sh-" + p.k })),
        inp, h("div", { class: "share" }, h("b", { id: "bar-" + p.k })), h("span", { class: "d", text: p.d })));
    }
    const adv = el("advbody"); adv.replaceChildren();
    for (const a of ADV) {
      const inp = h("input", { type: "range", min: a.min, max: a.max, step: a.step, value: state.P[a.k], id: "a-" + a.k, "aria-label": a.name });
      inp.addEventListener("input", () => { state.P[a.k] = +inp.value; schedule(); });
      adv.append(h("div", { class: "pill" }, h("div", { class: "row" }, h("span", { class: "nm", text: a.name }), h("span", { class: "sh", id: "av-" + a.k })), inp, h("span", { class: "d", text: a.d })));
    }
    el("default-lbl").textContent = `Default ${DEF.w.p1}/${DEF.w.p2}/${DEF.w.p3}`;
  }
  function buildMenu() {
    const btn = el("cmenu-btn"), menu = el("cmenu");
    const close = () => { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); };
    btn.addEventListener("click", (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; btn.setAttribute("aria-expanded", String(!menu.hidden)); });
    document.addEventListener("click", (e) => { if (!menu.hidden && !menu.contains(e.target) && e.target !== btn) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !menu.hidden) { close(); btn.focus(); } });
    const groups = h("div", { class: "grp" }, ...GROUPS.map((g) => h("button", { class: "btn", title: g.desc, text: `${g.name} (${g.c.length})`,
      onclick: () => { state.sel = g.c.slice(); render(); } })));
    const list = h("div", { class: "list" }, ...CODES.map((c) => {
      const cb = h("input", { type: "checkbox", "data-c": c, id: "cb-" + c });
      cb.addEventListener("change", () => { state.sel = cb.checked ? [...state.sel.filter((x) => x !== c), c] : state.sel.filter((x) => x !== c); render(); });
      return h("label", { for: "cb-" + c }, cb, h("i", {}), META[c].name);
    }));
    menu.replaceChildren(h("span", { class: "lbl", text: "Pick a group" }), groups, h("span", { class: "lbl", text: "Or tick countries" }), list,
      h("div", { class: "foot2" }, h("button", { class: "btn", text: "Clear all", onclick: () => { state.sel = []; render(); } }), h("button", { class: "btn", text: "Done", onclick: close })));
  }
  function updateRecipe() {
    const tot = state.P.w.p1 + state.P.w.p2 + state.P.w.p3;
    for (const p of PILLARS) {
      const share = p.off ? 0 : tot ? state.P.w[p.k] / tot : 0;
      el("sh-" + p.k).textContent = p.off ? `weight ${state.P.w[p.k]} · 0%` : `weight ${state.P.w[p.k]} · ${Math.round(share * 100)}%`;
      el("bar-" + p.k).style.width = share * 100 + "%";
    }
    for (const a of ADV) el("av-" + a.k).textContent = `${state.P[a.k]} ${a.unit}`;
    el("modified").hidden = JSON.stringify(state.P) === JSON.stringify(DEF);
  }
  function updateControls() {
    el("btn-all").setAttribute("aria-pressed", String(!state.sel.length));
    const n = state.sel.length;
    el("cmenu-btn").textContent = (n === 0 ? "Choose countries" : n === 1 ? META[state.sel[0]].name : `${n} countries`) + " ▾";
    document.querySelectorAll("#cmenu input[data-c]").forEach((cb) => {
      const i = state.sel.indexOf(cb.dataset.c); cb.checked = i >= 0;
      cb.parentElement.querySelector("i").style.background = i >= 0 ? `var(${col(i)})` : "transparent";
    });
    el("years-lbl").textContent = winLbl();
    el("oneyear").classList.toggle("on", single());
    if (single() && document.activeElement !== el("oneyear")) el("oneyear").value = state.from;
    const span = Y1 - Y0, l = ((state.from - Y0) / span) * 100, r = ((state.to - Y0) / span) * 100;
    el("range-fill").style.left = l + "%"; el("range-fill").style.width = r - l + "%";
    document.querySelectorAll("#measure button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.m === state.m)));
    document.querySelectorAll("#alltabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.t === state.tab)));
    updateRecipe();
  }
  const baseName = () => (GROUP[state.base] ? GROUP[state.base].the : state.base === "A" ? "the long-standing 10" : state.base === "B" ? "the Western 20" : "all countries with data");
  function p1Note(box) {
    box.replaceChildren();
    if (state.m === "p1") box.append(h("p", { class: "note", text: "The laws pillar scores each country against its own history, so it shows when a parliament was busier or quieter than usual. Comparing levels across countries says little." }));
    else if (isR()) box.append(h("p", { class: "note", text: "Position on the overall index each year, 1 = best. Countries are ranked among those with data that year: all 31 from 1993, fewer before (10 in the 1950s). Averages are average ranks." }));
    else if (state.m === "p2") box.append(h("p", { class: "note", text: "Budgets score 100 on time, 50 within the grace period and 0 when late or rolled over. The UK and Ireland are not scored." }));
  }

  // ---- all-countries view ----
  function renderAll() {
    const avg = avgSeries(), rk = ranking();
    const wv = mean(avg.filter((d) => d.v !== null && inWin(d.y)).map((d) => d.v));
    const ns = avg.filter((d) => inWin(d.y)).map((d) => d.n).filter((n) => n);
    const hl = el("headline"); hl.replaceChildren();
    const inBase = new Set(baseSet()), rkH = rk.filter((d) => inBase.has(d.c));
    if (rkH.length && isR()) {
      hl.append(`Across ${baseName()}, `, h("b", { text: META[rkH[0].c].name }), ` has the best average rank in ${winLbl()} (${f1(rkH[0].v)}), `, h("b", { text: META[rkH[rkH.length - 1].c].name }), ` the worst (${f1(rkH[rkH.length - 1].v)}).`);
    } else if (rkH.length) {
      hl.append(`Across ${baseName()}, the ${MEAS_SHORT[state.m]} averaged `, h("b", { text: f1(wv) }), ` in ${winLbl()}. `,
        h("b", { text: META[rkH[0].c].name }), ` ranks highest (${f1(rkH[0].v)}), `, h("b", { text: META[rkH[rkH.length - 1].c].name }), ` lowest (${f1(rkH[rkH.length - 1].v)}).`);
    }
    el("avg-title").textContent = isR() ? "European average: not shown for rankings" : `European average: ${MEAS[state.m].toLowerCase()}`;
    el("avg-dek").textContent = isR() ? "An average of ranks has no meaning, so this chart stays empty in Ranking. Pick countries to plot their positions, or use the heatmap and ranking below." : `Mean of ${baseName()} each year. The shaded band covers the middle half of countries.`;
    p1Note(el("p1-note-all"));
    lineChart(el("chart-avg"), { series: [], avg: isR() ? null : avg, label: "European average over time" });
    if (isR()) { el("legend-avg").replaceChildren(); } else el("legend-avg").replaceChildren(h("span", {}, h("i", { style: "background:var(--avg)" }), "Average"), h("span", {}, h("i", { class: "sq", style: "background:var(--band)" }), "Middle half of countries"));
    el("foot-avg").textContent = isR() ? "" : ns.length ? `Countries in the average: ${d3.min(ns)} to ${d3.max(ns)} per year. Countries join as their records start, so early decades describe fewer, mostly Western, democracies.` : "";
    const body = el("all-body"); body.replaceChildren();
    if (state.tab === "heat") heatmap(body, avg);
    else if (state.tab === "multi") multiples(body, avg);
    else rankTable(body, rk);
    el("foot-all").textContent = state.tab === "rank"
      ? `Window average of the ${MEAS_SHORT[state.m]}. Countries need data for at least a third of the window to rank. Change compares with ${single() ? `${state.from - 1}` : `the ${state.to - state.from + 1} years before ${state.from}`}.`
      : "Sorted by window average. Click a country to open it. Hatched cells have no data; pale cells are years before the country was scored.";
  }
  function heatmap(box, avg) {
    const wrap = h("div", { class: "chart" }); box.append(wrap);
    const W = Math.max(300, box.clientWidth), narrow = W < 560;
    const ys = viewYears(), lw = narrow ? 34 : 112, rw = 40, cw = (W - lw - rw) / ys.length, rh = narrow ? 14 : 16;
    const order = CODES.map((c) => ({ c, ...winAvg(c) })).sort(cmpV);
    const H = 22 + (order.length + 1) * rh + 10 + 22;
    const svg = d3.select(wrap).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("width", "100%").attr("role", "img").attr("aria-label", "Heatmap of scores by country and year");
    const pat = svg.append("defs").append("pattern").attr("id", "hatch").attr("width", 4).attr("height", 4).attr("patternUnits", "userSpaceOnUse").attr("patternTransform", "rotate(45)");
    pat.append("rect").attr("width", 4).attr("height", 4).style("fill", "var(--surface)");
    pat.append("line").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 4).style("stroke", "var(--hatch)").style("stroke-width", 2);
    const x = (yr) => lw + (yr - vFrom()) * cw;
    const tickStep = ys.length > 40 ? 10 : ys.length > 15 ? 5 : ys.length > 6 ? 2 : 1;
    svg.append("g").attr("class", "axis").selectAll("text").data(ys.filter((y) => y % tickStep === 0)).join("text")
      .attr("x", (y) => x(y) + cw / 2).attr("y", 12).attr("text-anchor", "middle").text((y) => y);
    svg.append("text").attr("x", W - rw / 2).attr("y", 12).attr("text-anchor", "middle").text("avg").style("fill", "var(--ink-3)").style("font-size", "11px");
    const rowsData = [...(isR() ? [] : [{ c: "_avg", name: narrow ? "Avg" : "Average", v: mean(avg.filter((d) => d.v !== null && inWin(d.y)).map((d) => d.v)) }]), ...order.map((o) => ({ c: o.c, name: narrow ? o.c : META[o.c].name, v: o.v }))];
    rowsData.forEach((row, i) => {
      const y0 = 22 + i * rh + (i && !isR() ? 8 : 0);
      const g = svg.append("g").style("cursor", row.c === "_avg" ? "default" : "pointer");
      g.append("text").attr("x", lw - 6).attr("y", y0 + rh / 2).attr("dy", "0.35em").attr("text-anchor", "end").text(row.name)
        .style("fill", "var(--ink)").style("font-size", "12px").style("font-weight", row.c === "_avg" ? 700 : 500);
      g.selectAll("rect").data(ys).join("rect").attr("x", (yr) => x(yr)).attr("y", y0).attr("width", Math.max(0.5, cw - (cw > 4 ? 1 : 0))).attr("height", rh - 2)
        .style("fill", (yr) => {
          if (row.c === "_avg") { const a = avg[yr - vFrom()]; return a.v === null ? "url(#hatch)" : scale(toScore(a.v)); }
          const r = RAW[row.c][yr - Y0]; const v = val(row.c, yr);
          if (r && r.pre) return "var(--pre)"; return v === null ? "url(#hatch)" : scale(toScore(v));
        })
        .on("pointermove", (e, yr) => {
          const v = row.c === "_avg" ? avg[yr - vFrom()].v : val(row.c, yr);
          const r = row.c === "_avg" ? null : RAW[row.c][yr - Y0];
          showTip(e, [h("div", { class: "tt", text: `${row.c === "_avg" ? "Average" : META[row.c].name}, ${yr}` }),
            h("div", { text: r && r.pre ? "Before democratic scoring starts" : v === null ? "No data" : isR() ? `Rank ${v} of ${SC[row.c][yr - Y0].rankN}` : `${MEAS[state.m]}: ${f1(v)}` })]);
        }).on("pointerleave", hideTip);
      g.append("text").attr("x", W - rw / 2).attr("y", y0 + rh / 2).attr("dy", "0.35em").attr("text-anchor", "middle").text(f1(row.v))
        .style("fill", "var(--ink-2)").style("font-family", "var(--mono)").style("font-size", "11px");
      if (row.c !== "_avg") g.on("click", () => { state.sel = [row.c]; render(); window.scrollTo({ top: 0 }); });
    });
    if (single()) svg.append("rect").attr("x", x(state.from) - 1).attr("y", 20).attr("width", cw + 1).attr("height", 22 + (order.length + 1) * rh + 8 - 20).style("fill", "none").style("stroke", "var(--ink)").style("stroke-width", 1.5);
    // legend
    const ly = H - 14, lx0 = lw, lwid = Math.min(220, W - lw - rw);
    const grad = svg.select("defs").append("linearGradient").attr("id", "lg");
    d3.range(0, 101, 10).forEach((t) => grad.append("stop").attr("offset", t + "%").attr("stop-color", scale(t)));
    svg.append("rect").attr("x", lx0).attr("y", ly - 6).attr("width", lwid).attr("height", 8).style("fill", "url(#lg)");
    [0, 50, 100].forEach((t) => svg.append("text").attr("x", lx0 + (t / 100) * lwid).attr("y", ly + 13).attr("text-anchor", t === 0 ? "start" : t === 100 ? "end" : "middle").text(isR() ? (t === 0 ? "31st" : t === 100 ? "1st" : "16th") : t).style("fill", "var(--ink-3)").style("font-size", "10px").style("font-family", "var(--mono)"));
    svg.append("rect").attr("x", lx0 + lwid + 16).attr("y", ly - 6).attr("width", 12).attr("height", 8).style("fill", "url(#hatch)").style("stroke", "var(--hatch)");
    svg.append("text").attr("x", lx0 + lwid + 32).attr("y", ly + 1).text("no data").style("fill", "var(--ink-3)").style("font-size", "11px");
  }
  function multiples(box, avg) {
    const order = CODES.map((c) => ({ c, ...winAvg(c) })).sort(cmpV);
    const grid = h("div", { class: "multi" }); box.append(grid);
    for (const o of order) {
      const b = h("button", { class: "mini", "aria-label": `Open ${META[o.c].name}`, onclick: () => { state.sel = [o.c]; render(); window.scrollTo({ top: 0 }); } },
        h("div", { class: "t" }, h("span", { text: META[o.c].name }), h("span", { text: f1(o.v) })));
      grid.append(b);
      const W = 150, H = 54;
      const svg = d3.select(b).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("width", "100%").attr("aria-hidden", "true");
      const x = d3.scaleLinear().domain([vFrom(), Math.max(vTo(), vFrom() + 1)]).range([2, W - 2]), y = d3.scaleLinear().domain(isR() ? [NC, 1] : [0, 100]).range([H - 3, 3]);
      if (single()) svg.append("rect").attr("x", x(state.from - 0.5)).attr("width", Math.max(2, x(state.from + 0.5) - x(state.from - 0.5))).attr("y", 0).attr("height", H).style("fill", "var(--accent-soft)");
      svg.append("line").attr("x1", 2).attr("x2", W - 2).attr("y1", y(isR() ? 16 : 50)).attr("y2", y(isR() ? 16 : 50)).attr("class", "gridline");
      if (!isR()) svg.append("path").datum(avg).style("fill", "none").style("stroke", "var(--avg)").style("stroke-width", 1.2).attr("d", d3.line().defined((d) => d.v !== null).x((d) => x(d.y)).y((d) => y(d.v)));
      const vs = viewYears().map((yr) => ({ y: yr, v: val(o.c, yr) }));
      svg.append("path").datum(vs).style("fill", "none").style("stroke", "var(--c1)").style("stroke-width", 1.8).attr("d", d3.line().defined((d) => d.v !== null).x((d) => x(d.y)).y((d) => y(d.v)));
    }
    box.append(h("div", { class: "legend" }, h("span", {}, h("i", { style: "background:var(--c1)" }), "Country"), h("span", {}, h("i", { style: "background:var(--avg)" }), "European average"), h("span", { text: "Number: window average" })));
  }
  function rankTable(box, rk) {
    const len = state.to - state.from + 1, pf = state.from - len, pt = state.from - 1;
    const prev = pf >= Y0 ? Object.fromEntries(ranking(pf, pt).map((d, i) => [d.c, i + 1])) : {};
    const t = h("table", { class: "rank" }); const tb = h("tbody"); t.append(tb);
    rk.forEach((d, i) => {
      const pr = prev[d.c]; const ch = pr ? pr - (i + 1) : null;
      const pnl = META[d.c].panelA ? "A" : META[d.c].panelB ? "B" : "C";
      tb.append(h("tr", { onclick: () => { state.sel = [d.c]; render(); window.scrollTo({ top: 0 }); } },
        h("td", { class: "n", text: i + 1 }),
        h("td", { class: "nm" }, META[d.c].name, h("span", { class: "badge", title: `Panel ${pnl}`, text: pnl })),
        h("td", { class: "barc" }, h("div", { class: "bar", style: `width:${Math.max(2, toScore(d.v))}%;background:${scale(toScore(d.v))}` })),
        h("td", { class: "val", text: f1(d.v) }),
        h("td", { class: "chg " + (ch > 0 ? "pos" : ch < 0 ? "neg" : ""), text: ch === null ? "" : ch > 0 ? `▲${ch}` : ch < 0 ? `▼${-ch}` : "=" , title: pr ? `Rank ${pr} in ${pf}–${pt}` : "" }),
        h("td", { class: "yrs", text: `${d.n} yrs` })));
    });
    box.append(h("div", { class: "scrollx" }, t));
    const missing = CODES.filter((c) => !rk.find((d) => d.c === c));
    if (missing.length) box.append(h("p", { class: "foot", text: `Not ranked (too few years with data in this window): ${missing.map((c) => META[c].name).join(", ")}.` }));
  }

  // ---- selected-countries view ----
  function renderSel() {
    const avg = avgSeries(), sel = state.sel, one = sel.length === 1;
    const series = sel.map((c, i) => ({ label: META[c].name, color: col(i), values: viewYears().map((y) => ({ y, v: val(c, y) })) }));
    const avgAt = Object.fromEntries(avg.map((d) => [d.y, d.v]));
    const rk = ranking(); const N = rk.length;
    const gap = (c) => { if (isR()) return null; const ds = years().map((y) => [val(c, y), avgAt[y] ?? null]).filter(([a, b]) => a !== null && b !== null); return ds.length ? mean(ds.map(([a, b]) => a - b)) : null; };
    const hl = el("headline"); hl.replaceChildren();
    if (sel.length > 4) {
      const ws = sel.map((c) => ({ c, ...winAvg(c) })).filter((d) => d.v !== null).sort(cmpV);
      if (ws.length) hl.append(`Of the ${sel.length} countries picked, `, h("b", { text: META[ws[0].c].name }), ` averaged highest in ${winLbl()} (${f1(ws[0].v)}) and `, h("b", { text: META[ws[ws.length - 1].c].name }), ` lowest (${f1(ws[ws.length - 1].v)}).`);
    } else sel.forEach((c, i) => {
      const w = winAvg(c), r = rk.findIndex((d) => d.c === c) + 1, g = gap(c);
      if (w.v === null) { hl.append(h("b", { text: META[c].name }), ` has no ${MEAS_SHORT[state.m]} data in ${winLbl()}. `); return; }
      if (isR()) { hl.append(h("b", { text: META[c].name }), single() ? ` ranked ${ord(w.v)} of ${SC[c][state.from - Y0].rankN}` : ` had an average rank of ${f1(w.v)}`, i === 0 ? ` in ${winLbl()}` : "", !single() && r ? `, ${ord(r)} of ${N} on that measure` : "", ". "); return; }
      hl.append(h("b", { text: META[c].name }), ` averaged ${f1(w.v)}`, i === 0 ? ` in ${winLbl()}` : "",
        g !== null ? `, ${Math.abs(g).toFixed(1)} ${g >= 0 ? "above" : "below"} the average` : "", r ? `, ${ord(r)} of ${N}` : "", ". ");
    });
    el("sel-title").textContent = `${sel.length > 4 ? `${sel.length} countries` : sel.map((c) => META[c].name).join(" vs ")}: ${MEAS[state.m].toLowerCase()}`;
    el("sel-dek").textContent = isR() ? "Position on the overall index each year. 1st is at the top." : `Against the average of ${baseName()} (dashed) and the middle half of countries (shaded).`;
    p1Note(el("p1-note-sel"));
    const notes = one ? NOTES.filter((n) => n.country === sel[0] && n.year >= vFrom() && n.year <= vTo()).sort((a, b) => a.year - b.year) : [];
    const plotted = notes.filter((n) => val(sel[0], n.year) !== null);
    const eras = one ? (META[sel[0]].eras || []).slice(1).map((y) => ({ y, label: "new era" })) : [];
    lineChart(el("chart-main"), { series, avg: isR() ? null : avg, notes: plotted, eras, label: "Selected countries over time" });
    el("legend-main").replaceChildren(...series.map((s) => h("span", {}, h("i", { style: `background:var(${s.color})` }), s.label)),
      ...(isR() ? [] : [h("span", {}, h("i", { style: "background:var(--avg)" }), "Average"), h("span", {}, h("i", { class: "sq", style: "background:var(--band)" }), "Middle half")]),
      ...(plotted.length ? [h("span", { text: "Numbered dots: events, listed below" })] : []));
    el("notes").replaceChildren(...plotted.map((n, i) => {
      const src = typeof n.source === "string" && /^https:\/\//.test(n.source) ? h("a", { href: n.source, target: "_blank", rel: "noopener", text: "Source" }) : null;
      return h("li", {}, h("span", { class: "no", text: i + 1 }), h("span", { class: "yr", text: n.year }), h("span", {}, h("b", { text: n.label + ". " }), (n.text || "") + " ", src));
    }));
    el("foot-main").textContent = sel.map(covLine).join(" ");
    const det = el("sec-detail"); det.replaceChildren();
    if (one) detail(det, sel[0], rk, gap); else compare(det, sel, rk);
  }
  function compare(box, sel, rk) {
    box.append(h("h2", { text: "Side by side" }), h("p", { class: "dek", text: `Window averages, ${winLbl()}. The index uses the current recipe.` }));
    const t = h("table", { class: "cmp" });
    t.append(h("thead", {}, h("tr", {}, ...["Country", "Index", "Laws", "Budgets", "Stability", "Rank", "Years"].map((s) => h("th", { text: s })))));
    const tb = h("tbody"); t.append(tb);
    sel.forEach((c, i) => {
      const r = rk.findIndex((d) => d.c === c) + 1;
      tb.append(h("tr", {}, h("td", {}, h("span", { class: "chip", style: "padding:2px 8px;border:none;background:none" }, h("i", { style: `background:var(${col(i)})` }), META[c].name)),
        ...["pei", "p1", "p2", "p3"].map((m) => h("td", { text: f1(winAvg(c, state.from, state.to, m).v) })),
        h("td", { text: r ? `${r}/${rk.length}` : "–" }), h("td", { text: winAvg(c, state.from, state.to, "pei").n })));
    });
    box.append(h("div", { class: "scrollx" }, t));
    box.append(h("p", { class: "foot", text: "Pick a single country to see its pillars, budgets and governments year by year." }));
  }
  function detail(box, c, rk, gap) {
    const w = winAvg(c), r = rk.findIndex((d) => d.c === c) + 1, g = gap(c);
    const vs = years().map((y) => ({ y, v: val(c, y) })).filter((d) => d.v !== null);
    const sv = vs.slice().sort(cmpV), best = sv.length ? sv[0] : null, worst = sv.length ? sv[sv.length - 1] : null;
    box.append(h("h2", { text: `Inside ${META[c].name}` }), h("p", { class: "dek", text: "What drives the index, year by year." }));
    const kp = (k, v, s, cls) => h("div", { class: "kpi" }, h("div", { class: "k", text: k }), h("div", { class: "v " + (cls || ""), text: v }), h("div", { class: "s", text: s }));
    box.append(h("div", { class: "kpis" },
      kp(`${MEAS[state.m]}, ${winLbl()}`, f1(w.v), `${w.n} years with data`),
      kp("Rank", r ? ord(r) : "–", r ? `of ${rk.length} countries` : "too few years to rank"),
      isR() ? kp("Countries ranked", String(SC[c][state.to - Y0].rankN || "–"), `with data in ${state.to}`) : kp("Gap to average", sgn(g), `vs ${baseName()}`, g === null ? "" : g >= 0 ? "pos" : "neg"),
      kp("Best and worst", best ? `${best.y} · ${worst.y}` : "–", best ? `${f1(best.v)} and ${f1(worst.v)}` : "")));
    // pillars chart
    box.append(h("div", { class: "strip-h" }, h("h3", { text: "The three pillars" })));
    const pc = h("div", { class: "chart" }); box.append(pc);
    const ps = [["p1", "Laws", "--c2"], ["p2", "Budgets", "--c3"], ["p3", "Stability", "--c4"]].map(([m, label, color]) => ({ label, color, width: 1.6, values: viewYears().map((y) => ({ y, v: val(c, y, m) })) }));
    ps.push({ label: "Index", color: "--c1", width: 3, values: viewYears().map((y) => ({ y, v: val(c, y, "pei") })) });
    lineChart(pc, { scoreScale: true, series: ps, height: pc.clientWidth < 560 ? 200 : 240, label: "Pillar scores" });
    box.append(h("div", { class: "legend" }, ...ps.map((s) => h("span", {}, h("i", { style: `background:var(${s.color})` }), s.label))));
    // contribution bar
    const W = state.P.w, contrib = { p1: [], p2: [], p3: [] }; let imputed = 0;
    for (const y of years()) {
      const s = SC[c][y - Y0]; if (!s || s.pei === null) continue;
      const p1 = s.p1 === null ? 50 : s.p1; if (s.p1 === null) imputed++;
      const parts = { p1: [W.p1, p1], p2: [W.p2, s.p2], p3: [W.p3, s.p3] };
      const den = Object.values(parts).reduce((a, [w, v]) => a + (v === null ? 0 : w), 0);
      for (const k in parts) contrib[k].push(parts[k][1] === null || !den ? 0 : (parts[k][0] * parts[k][1]) / den);
    }
    const cm = { p1: mean(contrib.p1), p2: mean(contrib.p2), p3: mean(contrib.p3) };
    if (cm.p1 !== null) {
      const tot = cm.p1 + cm.p2 + cm.p3;
      box.append(h("div", { class: "strip-h" }, h("h3", { text: "Where the index points come from" }), h("span", { class: "foot", style: "margin:0", text: `Average over the window, ${f1(tot)} in total` })));
      const bar = h("div", { style: "display:flex;height:26px;border-radius:4px;overflow:hidden;background:var(--band)" });
      [["p1", "Laws", "--c2"], ["p2", "Budgets", "--c3"], ["p3", "Stability", "--c4"]].forEach(([k, lab, col]) => {
        const seg = h("div", { style: `width:${cm[k]}%;background:var(${col});display:flex;align-items:center;padding-left:6px;color:var(--bg);font-size:12px;font-weight:700;white-space:nowrap;overflow:hidden` }, `${lab} ${f1(cm[k])}`);
        bar.append(seg);
      });
      box.append(bar);
      box.append(h("p", { class: "foot", text: `Each segment is the pillar's weighted share of the index, out of 100. ${imputed ? `Laws count as a neutral 50 in ${imputed} year${imputed > 1 ? "s" : ""} without law data.` : ""}` }));
    }
    budgetStrip(box, c);
    govStrip(box, c);
  }
  function budgetStrip(box, c) {
    box.append(h("div", { class: "strip-h" }, h("h3", { text: "Budget in force on day one" })));
    const cats = { ok: ["On time", "var(--ok)"], late: ["Late", "var(--warn)"], bad: ["Rolled over or provisional", "var(--bad)"], na: ["Not scored", "var(--rule)"], unk: ["Unknown", "url(#hatch2)"], pre: ["Before scoring", "var(--pre)"] };
    const cat = (r) => { if (!r || r.pre) return "pre"; if (r.reg === "structural_na") return "na"; if (r.inf === 1) return "ok"; if (r.inf === 0) return r.reg === "late" ? "late" : "bad"; return "unk"; };
    const wrap = h("div", { class: "chart" }); box.append(wrap);
    const W = Math.max(280, box.clientWidth - 36), ys = viewYears(), lw = 32, cw = (W - lw - 14) / ys.length, H = 46;
    const svg = d3.select(wrap).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("width", "100%").attr("role", "img").attr("aria-label", "Budget timeliness by year");
    const pat = svg.append("defs").append("pattern").attr("id", "hatch2").attr("width", 4).attr("height", 4).attr("patternUnits", "userSpaceOnUse").attr("patternTransform", "rotate(45)");
    pat.append("rect").attr("width", 4).attr("height", 4).style("fill", "var(--surface)"); pat.append("line").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 4).style("stroke", "var(--hatch)").style("stroke-width", 2);
    svg.selectAll("rect.c").data(ys).join("rect").attr("class", "c").attr("x", (y) => lw + (y - vFrom()) * cw).attr("y", 4).attr("width", Math.max(0.6, cw - (cw > 4 ? 1 : 0))).attr("height", 18)
      .style("fill", (y) => cats[cat(RAW[c][y - Y0])][1]).style("stroke", (y) => (single() && y === state.from ? "var(--ink)" : null)).style("stroke-width", 1.5)
      .on("pointermove", (e, y) => { const r = RAW[c][y - Y0]; const k = cat(r);
        showTip(e, [h("div", { class: "tt", text: `${y}: ${cats[k][0]}` }), r && r.inf === 0 && r.delay !== null ? h("div", { text: `${r.delay} days late` }) : null, r && r.reg && r.reg !== "structural_na" ? h("div", { text: `Recorded as: ${r.reg.replace("_", " ")}` }) : null].filter(Boolean)); })
      .on("pointerleave", hideTip);
    svg.append("g").attr("class", "axis").attr("transform", "translate(0,26)").call(d3.axisBottom(d3.scaleLinear().domain([vFrom(), vTo() + 1]).range([lw, lw + ys.length * cw])).ticks(Math.min(8, ys.length)).tickFormat(d3.format("d")).tickSize(3)).select(".domain").remove();
    const fy = META[c].fy, fyKeys = Object.keys(fy).map(Number).sort();
    const fyTxt = fyKeys.length > 1 ? `Fiscal year starts ${fyKeys.map((k, i) => `${fy[k].replace("-", "/")}${i ? ` from ${k}` : ""}`).join(", ")} (month/day).` : fy[fyKeys[0]] !== "01-01" ? `Fiscal year starts ${fy[fyKeys[0]].replace("-", "/")} (month/day).` : "";
    box.append(h("div", { class: "legend" }, ...["ok", "late", "bad", "unk", "na", "pre"].map((k) => h("span", {}, h("i", { class: "sq", style: `background:${k === "unk" ? "var(--hatch)" : cats[k][1]}` }), cats[k][0]))));
    if (fyTxt) box.append(h("p", { class: "foot", text: fyTxt }));
  }
  function govStrip(box, c) {
    box.append(h("div", { class: "strip-h" }, h("h3", { text: "Governments" })));
    const cabs = CABS.filter((k) => k.c === c && (!k.end || +k.end.slice(0, 4) >= vFrom()) && +k.start.slice(0, 4) <= vTo());
    const wrap = h("div", { class: "chart" }); box.append(wrap);
    if (!cabs.length) { wrap.append(h("p", { class: "foot", text: "No government records in this window." })); return; }
    const W = Math.max(280, box.clientWidth - 36), lw = 32, H = 92;
    const t = (s) => { const d = new Date(s + "T00:00:00Z"); return d.getUTCFullYear() + (d - Date.UTC(d.getUTCFullYear(), 0, 1)) / 31557600000; };
    const x = d3.scaleLinear().domain([vFrom(), vTo() + 1]).range([lw, W - 14]).clamp(true);
    const svg = d3.select(wrap).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("width", "100%").attr("role", "img").attr("aria-label", "Governments over time");
    const ylab = (yy, txt) => svg.append("text").attr("x", 0).attr("y", yy).attr("dy", "0.35em").text(txt).style("fill", "var(--ink-3)").style("font-size", "10px");
    ylab(14, "PM"); ylab(46, "Care"); ylab(66, "Snap");
    let lastPm = null, shade = 0;
    cabs.forEach((k) => {
      if (k.pm !== lastPm) { shade = 1 - shade; lastPm = k.pm; }
      const x0 = x(t(k.start)), x1 = x(k.end ? t(k.end) : vTo() + 1); if (x1 - x0 < 0.3) return;
      const g = svg.append("g");
      g.append("rect").attr("x", x0).attr("y", 4).attr("width", Math.max(0.5, x1 - x0 - 0.5)).attr("height", 22)
        .style("fill", k.caretaker ? "var(--warn)" : shade ? "var(--accent)" : "var(--accent-soft)").style("opacity", k.caretaker ? 0.85 : 1);
      if (x1 - x0 > 44) g.append("text").attr("x", x0 + 4).attr("y", 15).attr("dy", "0.35em").text(k.pm).style("font-size", "11px").style("font-weight", 600)
        .style("fill", shade && !k.caretaker ? "var(--on-accent)" : "var(--ink)").style("pointer-events", "none");
      g.on("pointermove", (e) => showTip(e, [h("div", { class: "tt", text: k.name }), h("div", { text: `PM ${k.pm || "n/a"}` }), h("div", { text: `${k.start} to ${k.end || "today"}` }),
        h("div", { text: (k.caretaker ? "Caretaker. " : "") + (k.type || "").replace(/_/g, " ") })])).on("pointerleave", hideTip);
    });
    const ys = viewYears(), cw = (x(vTo() + 1) - x(vFrom())) / ys.length;
    svg.selectAll("rect.care").data(ys).join("rect").attr("class", "care").attr("x", (y) => x(y)).attr("y", 38).attr("width", Math.max(0.5, cw - (cw > 4 ? 1 : 0))).attr("height", 14)
      .style("fill", "var(--warn)").style("opacity", (y) => { const r = RAW[c][y - Y0]; return r && !r.pre && r.care !== null ? Math.min(1, 0.06 + r.care * 1.4) : 0; })
      .on("pointermove", (e, y) => { const r = RAW[c][y - Y0]; showTip(e, [h("div", { class: "tt", text: String(y) }), h("div", { text: r && r.care !== null ? `Caretaker or no government: ${Math.round(r.care * 100)}% of the year` : "No data" }), r && r.pm ? h("div", { text: `PM changes: ${r.pm}` }) : null].filter(Boolean)); })
      .on("pointerleave", hideTip);
    svg.selectAll("path.snap").data(ys.filter((y) => { const r = RAW[c][y - Y0]; return r && !r.pre && r.early > 0; })).join("path").attr("class", "snap")
      .attr("d", d3.symbol(d3.symbolDiamond, 46)).attr("transform", (y) => `translate(${x(y) + cw / 2},66)`).style("fill", "var(--bad)")
      .on("pointermove", (e, y) => showTip(e, [h("div", { class: "tt", text: `${y}: early election` })])).on("pointerleave", hideTip);
    svg.append("g").attr("class", "axis").attr("transform", "translate(0,76)").call(d3.axisBottom(x).ticks(Math.min(8, ys.length)).tickFormat(d3.format("d")).tickSize(3)).select(".domain").remove();
    box.append(h("div", { class: "legend" }, h("span", {}, h("i", { class: "sq", style: "background:var(--accent)" }), "Prime ministers, alternating shades"),
      h("span", {}, h("i", { class: "sq", style: "background:var(--warn)" }), "Caretaker government (darker = more of the year)"),
      h("span", {}, h("i", { class: "sq", style: "background:var(--bad);transform:rotate(45deg) scale(.8)" }), "Early election")));
  }

  // ---- method page ----
  function renderMethod() {
    const cards = el("pillar-cards"); cards.replaceChildren();
    const txt = [
      ["Laws passed", DEF.w.p1, "Substantive laws enacted in the year, as a three-year rolling average. Budget laws, treaty ratifications and pure amendments are excluded where the source allows. Scored as a percentile of the country's own history within its era. Where a pass rate for government bills exists it is averaged in."],
      ["Budget on time", DEF.w.p2, "Was spending authority in force on the first day of the fiscal year? 100 if yes, 50 if adopted within the grace period, 0 if later, rolled over or run on provisional twelfths."],
      ["Government stability", DEF.w.p3, "Share of the year with a government holding full powers, minus 15 points for an early election and 10 for each change of prime minister (two at most)."],
    ];
    txt.forEach(([n, w, d]) => cards.append(h("div", {}, h("h3", {}, n, h("span", { text: `weight ${w}` })), h("p", { text: d }))));
    el("formula").textContent = `index = Σ wᵢ·pillarᵢ / Σ wᵢ   over pillars with data that year\nstability = 100 × (1 − caretaker share) − ${DEF.snap} × early election − ${DEF.pm} × min(PM changes, 2)\nbudget = 100 on time · 50 within ${DEF.grace} days · 0 later`;
    const tb = document.querySelector("#sources tbody"); tb.replaceChildren();
    for (const c of CODES) { const s = PEI.sources[c] || {}; tb.append(h("tr", {}, h("td", { text: META[c].name }), h("td", { text: s.laws || "" }), h("td", { text: s.budget || "" }))); }
    el("built").textContent = `Data built ${PEI.built}. ${ROWS.filter((r) => r.pei !== null).length} scored country-years.`;
    coverageChart();
  }
  function coverageChart() {
    const box = el("chart-coverage"); box.replaceChildren();
    const W = Math.max(560, box.clientWidth), lw = 110, rh = 15, order = [...PANEL_A, ...PANEL_B.filter((c) => !PANEL_A.includes(c)), ...CODES.filter((c) => !PANEL_B.includes(c))];
    const H = 24 + order.length * rh + 30;
    const x = d3.scaleLinear().domain([Y0, Y1 + 1]).range([lw, W - 10]);
    const svg = d3.select(box).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("width", W).style("max-width", "none").style("width", "100%").style("min-width", "560px").attr("role", "img").attr("aria-label", "Data coverage by country");
    svg.append("g").attr("class", "axis").attr("transform", "translate(0,16)").call(d3.axisTop(x).tickValues(d3.range(1950, 2030, 10)).tickFormat(d3.format("d")).tickSize(0)).select(".domain").remove();
    const kinds = [["laws", (r) => r.p1b !== null, "var(--c2)"], ["budget", (r) => r.inf !== null, "var(--c3)"], ["govt", (r) => r.care !== null, "var(--c4)"]];
    order.forEach((c, i) => {
      const y0 = 24 + i * rh + (i >= PANEL_A.length ? 6 : 0) + (i >= PANEL_B.length ? 6 : 0);
      svg.append("text").attr("x", lw - 6).attr("y", y0 + rh / 2 - 1).attr("dy", "0.35em").attr("text-anchor", "end").text(META[c].name).style("fill", "var(--ink)").style("font-size", "11px");
      const pre = META[c].from > Y0 ? META[c].from : null;
      if (pre) svg.append("rect").attr("x", x(Y0)).attr("y", y0).attr("width", x(Math.min(pre, Y1 + 1)) - x(Y0)).attr("height", rh - 3).style("fill", "var(--pre)");
      kinds.forEach(([k, f, col], j) => {
        for (const r of RAW[c]) if (r && !r.pre && f(r)) svg.append("rect").attr("x", x(r.y)).attr("y", y0 + j * 4).attr("width", x(r.y + 1) - x(r.y) + 0.3).attr("height", 3).style("fill", col);
      });
      if (META[c].structural || COV[c].structural) svg.append("text").attr("x", W - 12).attr("y", y0 + 5).attr("text-anchor", "end").text("budget n/a").style("fill", "var(--ink-3)").style("font-size", "9px");
    });
    [[0, "Panel A · long history"], [PANEL_A.length, "Panel B · Western 20"], [PANEL_B.length, "Panel C · all 31"]].forEach(([i, t], k) => {
      const y0 = 24 + i * rh + k * 6 - 3;
      if (k) svg.append("line").attr("x1", 0).attr("x2", W).attr("y1", y0).attr("y2", y0).style("stroke", "var(--rule)");
    });
    el("legend-coverage").replaceChildren(h("span", {}, h("i", { style: "background:var(--c2)" }), "Laws"), h("span", {}, h("i", { style: "background:var(--c3)" }), "Budget dates"),
      h("span", {}, h("i", { style: "background:var(--c4)" }), "Governments"), h("span", {}, h("i", { class: "sq", style: "background:var(--pre)" }), "Before democratic scoring"),
      h("span", { text: "Rows: panel A first, then the rest of panel B, then panel C." }));
  }

  // ---- routing + render ----
  let page = location.hash === "#method" ? "method" : "explore";
  function go(name) {
    page = name;
    try { history.replaceState(null, "", "#" + name); } catch (e) { /* sandboxed frame: keep state in the page */ }
    route(); window.scrollTo({ top: 0 });
  }
  el("nav-explore").addEventListener("click", (e) => { e.preventDefault(); go("explore"); });
  el("nav-method").addEventListener("click", (e) => { e.preventDefault(); go("method"); });
  function route() {
    const m = page === "method";
    el("page-explore").hidden = m; el("page-method").hidden = !m;
    el("nav-explore").setAttribute("aria-current", m ? "false" : "page"); el("nav-method").setAttribute("aria-current", m ? "page" : "false");
    if (m) renderMethod(); else render();
  }
  document.querySelectorAll("[data-jump]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); const t = el(a.dataset.jump); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); }));
  function render() {
    if (el("page-explore").hidden) return;
    hideTip(); updateControls();
    const all = !state.sel.length;
    el("view-all").hidden = !all; el("view-sel").hidden = all;
    if (all) renderAll(); else renderSel();
  }
  let rt = 0, lastW = 0;
  new ResizeObserver(() => { const w = el("main").clientWidth || el("page-method").clientWidth; if (Math.abs(w - lastW) < 8) return; lastW = w; clearTimeout(rt); rt = setTimeout(() => (el("page-method").hidden ? render() : coverageChart()), 120); }).observe(document.body);
  const retheme = () => { makeScale(); route(); };
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", retheme);
  new MutationObserver(retheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  window.addEventListener("hashchange", () => { page = location.hash === "#method" ? "method" : "explore"; route(); });
  window.addEventListener("scroll", hideTip, { passive: true });

  makeScale(); rescore(); buildControls(); route();
})();
