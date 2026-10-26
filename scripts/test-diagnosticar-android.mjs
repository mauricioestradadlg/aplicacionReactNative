import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';

const script = fileURLToPath(new URL('./diagnosticar-android.mjs', import.meta.url));

async function backend(t, handler) {
  const server = createServer(handler);
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  t.after(() => {
    server.closeAllConnections();
    return new Promise(resolve => server.close(resolve));
  });
  return server;
}

function diagnose(url, { args = [], env = {}, preload } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [...(preload ? ['--import', pathToFileURL(preload).href] : []), script, ...args], {
      env: {
        ...process.env,
        EXPO_PUBLIC_API_URL_ANDROID: url,
        ANDROID_HOME: '', ANDROID_SDK_ROOT: '', LOCALAPPDATA: '', PATH: '', Path: '',
        ...env,
      },
      windowsHide: true,
      timeout: 10000,
    });
    let output = '';
    child.stdout.on('data', chunk => { output += chunk; });
    child.stderr.on('data', chunk => { output += chunk; });
    child.once('error', reject);
    child.once('close', code => resolve({ code, output }));
  });
}

function adbFixture(t, { sdk = 37, targetSdk = 37, granted = false } = {}) {
  const prefix = join(tmpdir(), 'meg-android-adb-test-');
  const directory = mkdtempSync(prefix);
  t.after(() => {
    const target = resolve(directory);
    assert.ok(target.startsWith(resolve(prefix)) && target.startsWith(resolve(tmpdir()) + sep));
    rmSync(target, { recursive: true, force: true });
  });
  const callsPath = join(directory, 'calls.jsonl');
  const preload = join(directory, 'adb-fixture.mjs');
  writeFileSync(callsPath, '');
  // El fixture reemplaza solo adb dentro del proceso de diagnóstico. No ejecuta
  // comandos Android reales ni modifica permisos del emulador del usuario.
  writeFileSync(preload, `
    import childProcess from 'node:child_process';
    import fs from 'node:fs';
    import { join } from 'node:path';
    import { syncBuiltinESMExports } from 'node:module';
    const adb = join(process.env.ANDROID_HOME, 'platform-tools', process.platform === 'win32' ? 'adb.exe' : 'adb');
    const exists = fs.existsSync;
    fs.existsSync = path => path === adb || exists(path);
    childProcess.spawnSync = (command, args) => {
      if (command !== adb) throw new Error('Unexpected executable');
      fs.appendFileSync(${JSON.stringify(callsPath)}, JSON.stringify(args) + '\\n');
      let stdout;
      if (args[0] === 'devices') stdout = 'List of devices attached\\nemulator-5554\\tdevice\\n';
      else if (args.includes('getprop')) stdout = ${JSON.stringify(String(sdk))};
      else if (args.includes('dumpsys')) stdout = ${JSON.stringify(`targetSdk=${targetSdk}\n${granted === null ? '' : `android.permission.ACCESS_LOCAL_NETWORK: granted=${granted}, flags=[]\n`}`)};
      else if (args.at(-1).includes('nc -w')) {
        const payload = args.at(-1).match(/printf %s '([^']+)'/)[1];
        const request = Buffer.from(payload, 'base64').toString();
        stdout = 'HTTP/1.1 ' + (request.includes('/csrf/') ? '200 OK' : '401 Unauthorized') + '\\r\\n\\r\\nprivate-body';
      } else throw new Error('Unexpected adb command');
      return { status: 0, stdout, stderr: '' };
    };
    syncBuiltinESMExports();
  `);
  return {
    preload,
    env: { ANDROID_HOME: directory },
    calls: () => readFileSync(callsPath, 'utf8').trim().split('\n').filter(Boolean).map(line => JSON.parse(line)),
  };
}

async function healthyBackend(t) {
  return backend(t, (request, response) => {
    response.writeHead(request.url.endsWith('/csrf/') ? 200 : 401);
    response.end('{}');
  });
}

test('detecta Django apagado antes de buscar adb y explica cómo iniciarlo', async t => {
  const server = await backend(t, (_request, response) => response.end());
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  const result = await diagnose(`http://127.0.0.1:${port}`);
  assert.equal(result.code, 1);
  assert.match(result.output, /Django no responde desde esta PC.*conexión rechazada/);
  assert.match(result.output, /runserver 0\.0\.0\.0:/);
  assert.doesNotMatch(result.output, /No se encontró adb/);
});

test('comprueba 10.0.2.2 desde loopback conservando Host y sin mostrar tokens', async t => {
  const requests = [];
  const server = await backend(t, (request, response) => {
    requests.push({ path: request.url, method: request.method, headers: request.headers });
    response.writeHead(request.url.endsWith('/csrf/') ? 200 : 401, {
      'Content-Type': 'application/json', 'Set-Cookie': 'private-cookie-value',
    });
    response.end(JSON.stringify({ csrfToken: 'private-token-value' }));
  });
  const port = server.address().port;
  const result = await diagnose(`http://10.0.2.2:${port}`);
  assert.equal(result.code, 1); // No hay adb en el entorno aislado de la prueba.
  assert.match(result.output, /PC: GET http:\/\/127\.0\.0\.1:.*HTTP 200/);
  assert.match(result.output, /HTTP 401 \(esperado 401\)/);
  assert.match(result.output, /El backend responde desde la PC\. No se encontró adb/);
  assert.doesNotMatch(result.output, /private-cookie|private-token|csrfToken/);
  assert.deepEqual(requests.map(request => [request.method, request.path]), [
    ['GET', '/api/sistema/app/csrf/'], ['GET', '/api/sistema/app/yo/'],
  ]);
  for (const request of requests) {
    assert.equal(request.headers.host, `10.0.2.2:${port}`);
    assert.equal(request.headers.authorization, undefined);
    assert.equal(request.headers.cookie, undefined);
  }
});

for (const [status, hint] of [
  [400, /ALLOWED_HOSTS/],
  [404, /no tiene las rutas/],
  [503, /NEON_MOBILE_DATABASE_URL/],
]) {
  test(`distingue HTTP ${status} de un fallo de red o de adb`, async t => {
    const server = await backend(t, (_request, response) => {
      response.writeHead(status);
      response.end('private-body-value');
    });
    const result = await diagnose(`http://127.0.0.1:${server.address().port}`);
    assert.equal(result.code, 1);
    assert.match(result.output, new RegExp(`El backend responde desde la PC, pero devolvió HTTP ${status}`));
    assert.match(result.output, hint);
    assert.doesNotMatch(result.output, /Django no responde|No se encontró adb|private-body/);
  });
}

test('rechaza URLs con credenciales sin exponerlas ni buscar adb', async () => {
  const result = await diagnose('http://private-user:private-password@localhost:8000');
  assert.equal(result.code, 1);
  assert.match(result.output, /sin credenciales/);
  assert.doesNotMatch(result.output, /private-|No se encontró adb|PC: GET/);
});

test('detecta permiso de red local denegado en Expo Go antes de consultar con nc', async t => {
  const server = await healthyBackend(t);
  const fixture = adbFixture(t);
  const result = await diagnose(`http://127.0.0.1:${server.address().port}`, fixture);
  assert.equal(result.code, 1);
  assert.match(result.output, /ACCESS_LOCAL_NETWORK está denegado/);
  assert.match(result.output, /Ajustes > Apps > Expo Go > Permisos > Dispositivos cercanos \/ Red local/);
  assert.match(result.output, /nc usan el usuario shell/);
  assert.match(result.output, /No se modificaron permisos/);
  const calls = fixture.calls();
  assert.ok(calls.some(args => args.includes('host.exp.exponent')));
  assert.ok(calls.every(args => !args.some(value => /nc -w|^grant$|^revoke$/.test(value))));
});

test('permiso concedido permite continuar y respeta --serial y --package de una compilación propia', async t => {
  const server = await healthyBackend(t);
  const fixture = adbFixture(t, { granted: true });
  const result = await diagnose(`http://127.0.0.1:${server.address().port}`, {
    ...fixture, args: ['--package', 'com.empresa.app', '--serial', 'emulator-5554'],
  });
  assert.equal(result.code, 0);
  assert.match(result.output, /Permiso de red local de com\.empresa\.app: concedido/);
  assert.doesNotMatch(result.output, /private-body|denegado/);
  const calls = fixture.calls();
  assert.ok(calls.some(args => args.includes('com.empresa.app')));
  assert.equal(calls.filter(args => args.some(value => value.includes('nc -w'))).length, 2);
  for (const args of calls.filter(args => args[0] !== 'devices')) assert.deepEqual(args.slice(0, 2), ['-s', 'emulator-5554']);
});

test('Android anterior a API 37 continúa sin exigir ACCESS_LOCAL_NETWORK', async t => {
  const server = await healthyBackend(t);
  const fixture = adbFixture(t, { sdk: 36 });
  const result = await diagnose(`http://127.0.0.1:${server.address().port}`, fixture);
  assert.equal(result.code, 0);
  assert.ok(fixture.calls().every(args => !args.includes('dumpsys')));
  assert.doesNotMatch(result.output, /denegado/);
});

test('Android 17 detecta denegación explícita incluso con targetSdk anterior', async t => {
  const server = await healthyBackend(t);
  const fixture = adbFixture(t, { targetSdk: 36 });
  const result = await diagnose(`http://127.0.0.1:${server.address().port}`, fixture);
  assert.equal(result.code, 1);
  assert.match(result.output, /ACCESS_LOCAL_NETWORK está denegado/);
  assert.match(result.output, /targetSdk anterior a 37 por ajustes de compatibilidad/);
  assert.ok(fixture.calls().every(args => !args.some(value => value.includes('nc -w'))));
});

test('Android 17 permite un paquete legado sin registro del permiso nuevo', async t => {
  const server = await healthyBackend(t);
  const fixture = adbFixture(t, { targetSdk: 36, granted: null });
  const result = await diagnose(`http://127.0.0.1:${server.address().port}`, fixture);
  assert.equal(result.code, 0);
  assert.doesNotMatch(result.output, /está denegado/);
});

test('rechaza flags repetidas o paquetes inválidos antes de consultar la red', async () => {
  for (const args of [['--serial', 'one', '--serial', 'two'], ['--package', 'com.app;grant']]) {
    const result = await diagnose('http://127.0.0.1:1', { args });
    assert.equal(result.code, 1);
    assert.doesNotMatch(result.output, /Django no responde|PC: GET/);
  }
});
