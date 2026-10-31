// Captura de RailRadar con datos REALES (se ejecuta en GitHub Actions)
import { chromium } from "playwright";
const out = process.argv[2] || "smoke_out";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1400, height: 900 } });
const errs = [];
p.on("pageerror", (e) => errs.push(e.message));
await p.goto("http://127.0.0.1:8000/");
await p.waitForTimeout(12000);
await p.screenshot({ path: `${out}/real_ld_estaciones.png` });
await p.check("#l-cer"); await p.waitForTimeout(2000);
await p.screenshot({ path: `${out}/real_todas_capas.png` });
// zoom Madrid y abrir una estación con trenes
await p.evaluate(() => map.jumpTo({ center: [-3.69, 40.41], zoom: 10 }));
await p.waitForTimeout(3000);
const pt = await p.evaluate(() => { const f = map.queryRenderedFeatures({ layers: ["stations"] })[0]; return f ? map.project(f.geometry.coordinates) : null; });
if (pt) { await p.uncheck("#l-cer"); await p.uncheck("#l-ld"); await p.mouse.click(pt.x, pt.y); await p.waitForTimeout(800); }
await p.screenshot({ path: `${out}/real_madrid_estacion.png` });
const counts = await p.evaluate(() => ["k-ld", "k-cer", "k-st"].map((i) => document.getElementById(i).textContent));
console.log(JSON.stringify({ counts, errors: errs }));
await b.close();
