// PEI scoring, mirrors pipeline/score.py. Pure functions; shared by the page and check_score.js.
(function (root) {
  const clip = (v) => Math.max(0, Math.min(100, v));
  const isNum = (v) => v !== null && v !== undefined && !Number.isNaN(v);

  // Expand the columnar export into objects once.
  function expand(PEI) {
    const ix = Object.fromEntries(PEI.cols.map((c, i) => [c, i]));
    return PEI.rows.map((r) => {
      const o = {};
      for (const k in ix) o[k] = r[ix[k]];
      return o;
    });
  }

  // P = {w:{p1,p2,p3,p4}, snap, pm, grace, decree}
  function scoreRow(r, P) {
    if (r.pre) return { p1: null, p2: null, p3: null, pei: null, imputed: false };
    let p1 = null;
    if (isNum(r.p1b)) p1 = clip(r.p1b - P.decree * (isNum(r.dec) ? r.dec : 0));
    let p2 = null;
    if (r.inf === 1) p2 = 100;
    else if (r.inf === 0) {
      if (r.reg === "late") p2 = isNum(r.delay) ? (r.delay <= P.grace ? 50 : 0) : 25;
      else p2 = 0;
    }
    let p3 = null;
    if (isNum(r.care)) p3 = clip(100 * (1 - r.care) - P.snap * (r.early || 0) - P.pm * Math.min(r.pm || 0, 2));
    if (p1 === null && p2 === null && p3 === null) return { p1, p2, p3, pei: null, imputed: false };
    const p1c = p1 === null ? 50 : p1;
    const parts = [[P.w.p1, p1c], [P.w.p2, p2], [P.w.p3, p3]];
    let num = 0, den = 0;
    for (const [w, v] of parts) if (v !== null) { num += w * v; den += w; }
    return { p1, p2, p3, pei: den ? num / den : null, imputed: p1 === null };
  }

  root.PEIScore = { expand, scoreRow };
  if (typeof module !== "undefined") module.exports = root.PEIScore;
})(typeof window !== "undefined" ? window : globalThis);
