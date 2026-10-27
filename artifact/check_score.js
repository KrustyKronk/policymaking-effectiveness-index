// node artifact/check_score.js : default parameters must reproduce stored pei (<= 0.01).
const fs = require("fs"), path = require("path");
const S = require("./pei-score.js");
const PEI = JSON.parse(fs.readFileSync(path.join(__dirname, "pei-data.json"), "utf8"));
const rows = S.expand(PEI), d = PEI.defaults;
const pw = PEI.pipelineW || d.w;  // stored pei was scored with the pipeline weights
const P = { w: { p1: pw.p1_throughput, p2: pw.p2_fiscal, p3: pw.p3_stability, p4: pw.p4_implementation },
            snap: d.snap, pm: d.pm, grace: d.grace, decree: d.decree };
let max = 0, n = 0, bad = [], nulls = 0;  // tolerance 0.025: stored inputs (caretaker share) are rounded to 3 dp
for (const r of rows) {
  const s = S.scoreRow(r, P);
  const a = r.pei, b = s.pei;
  if ((a === null) !== (b === null)) { nulls++; bad.push([r.c, r.y, a, b]); continue; }
  if (a !== null) { n++; const dd = Math.abs(a - b); if (dd > max) max = dd; if (dd > 0.03) bad.push([r.c, r.y, a, b]); }
}
console.log(`compared ${n} scored rows; max diff ${max.toFixed(4)}; mismatches ${bad.length} (null-pattern ${nulls})`);
if (bad.length) console.log(bad.slice(0, 10));
// 100/0/0 => pei equals P1 (or 50 where imputed)
const Q = { ...P, w: { p1: 100, p2: 0, p3: 0, p4: 0 } };
let off = 0;
for (const r of rows) { const s = S.scoreRow(r, Q); if (s.pei !== null && Math.abs(s.pei - (s.p1 === null ? 50 : s.p1)) > 1e-9) off++; }
console.log(`weights 100/0/0: rows where index != P1 = ${off}`);
// Spot checks from FINDINGS
const avg = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
const by = (f) => rows.filter(f).map((r) => S.scoreRow(r, P).pei).filter((v) => v !== null);
const A = new Set(["UK","IE","IT","DE","AT","DK","FR","LU","FI","IS"]);
for (const dec of [1950, 1990, 2000, 2010, 2020]) console.log(`Panel A ${dec}s`, avg(by((r) => A.has(r.c) && r.y >= dec && r.y < dec + 10)).toFixed(1));
const rank = Object.keys(PEI.countries).map((c) => [c, avg(by((r) => r.c === c && r.y >= 2016 && r.y <= 2025))]).sort((a, b) => a[1] - b[1]);
console.log("bottom 2016-25", rank.slice(0, 5).map(([c, v]) => `${c} ${v.toFixed(1)}`).join(", "));
console.log("Italy 1970s", avg(by((r) => r.c === "IT" && r.y >= 1970 && r.y < 1980)).toFixed(1), "1980s", avg(by((r) => r.c === "IT" && r.y >= 1980 && r.y < 1990)).toFixed(1));
{ const E = { ...P, w: { p1: d.w.p1_throughput, p2: d.w.p2_fiscal, p3: d.w.p3_stability, p4: 0 } };
  const rk = Object.keys(PEI.countries).map((c) => [c, avg(rows.filter((r) => r.c === c && r.y >= 2016 && r.y <= 2025).map((r) => S.scoreRow(r, E).pei).filter((v) => v !== null))]).sort((a, b) => a[1] - b[1]);
  console.log("explorer defaults, bottom 2016-25", rk.slice(0, 5).map(([c, v]) => `${c} ${v.toFixed(1)}`).join(", "), "| top", rk.slice(-4).reverse().map(([c, v]) => `${c} ${v.toFixed(1)}`).join(", ")); }
process.exit(bad.length || off ? 1 : 0);
