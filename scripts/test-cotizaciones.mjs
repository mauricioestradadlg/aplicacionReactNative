import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import vm from 'node:vm';
const require = createRequire(import.meta.url);
const ts = require('typescript');
const exportsCalculos = {};
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/features/quotes/calculos.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, { exports: exportsCalculos, Intl, Date, Object });
const exportsDocumento = {};
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/features/quotes/documento.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, { exports: exportsDocumento, require: () => exportsCalculos, Intl, Date });
const { calcularCotizacion, nuevaCotizacion } = exportsCalculos;
test('precios finales: no vuelve a añadir IVA a la landing', () => {
  const r = calcularCotizacion(nuevaCotizacion());
  assert.equal(r.totalInicial, 3500);
  assert.equal(r.primerPago, 1750);
  assert.equal(r.saldoDesarrollo, 1750);
  assert.equal(Math.round((r.baseSinIVA + r.ivaIncluido) * 100), 350000);
});
test('descuento solo al desarrollo; dominio completo en primer pago; mantenimiento excluye dominio', () => {
  const r = calcularCotizacion({ ...nuevaCotizacion(), servicio: 'sitio-web', formulario: true, panel: true, cantidadFunciones: 2, descuento: 'plantilla', dominio: '.mx', costoDominio: 295, mantenimiento: true });
  assert.equal(r.brutoDesarrollo, 14000);
  assert.equal(r.desarrollo, 12600);
  assert.equal(r.totalDominio, 595);
  assert.equal(r.totalInicial, 13195);
  assert.equal(r.primerPago, 6895);
  assert.equal(r.saldoDesarrollo, 6300);
  assert.equal(r.mensualidad, 1260);
});
test('descuentos alternativos y límites de funcionalidades de la web', () => {
  const r = calcularCotizacion({ ...nuevaCotizacion(), descuento: 'diseno', cantidadFunciones: 30.9 });
  assert.equal(r.conceptos[1].cantidad, 20);
  assert.equal(r.descuentoPct, 0.2);
  assert.equal(r.desarrollo, 34800);
});
test('texto del cliente se escapa en el PDF y conserva condiciones comerciales', () => {
  const html = exportsDocumento.documentoCotizacion({ ...nuevaCotizacion(), nombre: '<script>alert(1)</script>', negocio: 'A&B', referido: true, mantenimiento: true });
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(html.includes('A&amp;B'));
  assert.ok(html.includes('30 días adicionales'));
  assert.ok(html.includes('garantía'));
  assert.ok(html.includes('mantenimiento opcional'));
});
