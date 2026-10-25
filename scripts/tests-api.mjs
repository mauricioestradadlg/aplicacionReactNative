// Run with Node 22+: node --test scripts/tests-api.mjs
// Exercise the real API module with isolated native/browser adapters. No network,
// device storage, database or extra test dependencies are used.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const source = readFileSync(new URL('../src/services/api.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  fileName: 'api.ts',
}).outputText;

const reply = (body, status = 200) => ({
  status, ok: status >= 200 && status < 300, json: async () => body,
});
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

function loadApi({ platform = 'android', url = 'https://api.example.test/', dev = true, fetch: fetchImpl, secureStore: storeOverrides = {} } = {}) {
  const requests = [];
  const storage = new Map();
  const storageCalls = [];
  const timers = new Map();
  let timerId = 0;
  let fetchHandler = fetchImpl || (async () => reply({ ok: true }));
  const secureStore = {
    async getItemAsync(key) { storageCalls.push(['get', key]); return storage.get(key) ?? null; },
    async setItemAsync(key, value) { storageCalls.push(['set', key, value]); storage.set(key, value); },
    async deleteItemAsync(key) { storageCalls.push(['delete', key]); storage.delete(key); },
    ...storeOverrides,
  };
  const forbiddenStorage = new Proxy({}, {
    get() { throw new Error('Session credentials must never access browser storage.'); },
  });
  const module = { exports: {} };
  const context = {
    module, exports: module.exports, process: { env: { EXPO_PUBLIC_API_URL: url } },
    __DEV__: dev, AbortController, console,
    localStorage: forbiddenStorage, sessionStorage: forbiddenStorage,
    window: { localStorage: forbiddenStorage, sessionStorage: forbiddenStorage },
    setTimeout(callback, ms) { const id = ++timerId; timers.set(id, { callback, ms }); return id; },
    clearTimeout(id) { timers.delete(id); },
    async fetch(requestUrl, options) {
      requests.push({ url: requestUrl, ...options });
      return fetchHandler(requestUrl, options);
    },
    require(name) {
      if (name === 'react-native') return { Platform: { OS: platform } };
      if (name === 'expo-secure-store') return secureStore;
      throw new Error(`Unexpected dependency: ${name}`);
    },
  };
  vm.runInNewContext(compiled, context, { filename: 'src/services/api.ts' });
  return {
    api: module.exports, requests, storage, storageCalls, timers,
    setFetch(handler) { fetchHandler = handler; },
  };
}

test('native login uses mobile endpoints and JSON without cookies or a stored session', async () => {
  const challenge = { ok: true, verificacion_id: 'challenge-id', correo_oculto: 'us***@example.test' };
  const { api, requests, storageCalls } = loadApi({ fetch: async () => reply(challenge) });
  assert.equal(api.rutaAuth('login'), 'movil/login/');
  assert.equal(api.rutaAuth('verificar'), 'movil/verificar/');
  assert.deepEqual(await api.peticionSistema(api.rutaAuth('login'), {
    metodo: 'POST', datos: { usuario: 'admin', contrasena: 'test-password' },
  }), challenge);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, 'https://api.example.test/api/sistema/movil/login/');
  assert.equal(requests[0].credentials, 'omit');
  assert.equal(requests[0].headers['Content-Type'], 'application/json');
  assert.equal(requests[0].headers.Authorization, undefined);
  assert.equal(requests[0].headers['X-CSRFToken'], undefined);
  assert.deepEqual(JSON.parse(requests[0].body), { usuario: 'admin', contrasena: 'test-password' });
  assert.equal(storageCalls.length, 0);
});

test('native sessions use SecureStore and explicit Bearer while omitting cookies', async () => {
  const { api, requests, storage, storageCalls } = loadApi();
  assert.equal(api.hayToken(), false);
  await api.guardarToken('native-secret-token');
  assert.equal(storage.get('meg.sistema.sesion'), 'native-secret-token');
  await api.restaurarToken();
  await api.peticionSistema('gestion-ventas/id/liquidacion/', { metodo: 'POST', datos: { fuente: 'whatsapp' } });
  assert.equal(api.hayToken(), true);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].headers.Authorization, 'Bearer native-secret-token');
  assert.equal(requests[0].headers['X-CSRFToken'], undefined);
  assert.equal(requests[0].credentials, 'omit');
  assert.equal(requests[0].cache, 'no-store');
  assert.deepEqual(storageCalls.map(call => call[0]), ['set', 'get']);
});

test('web uses cookie sessions and cached CSRF, with no Bearer or browser storage', async () => {
  const { api, requests, storageCalls } = loadApi({
    platform: 'web',
    fetch: async url => reply(url.endsWith('/csrf/') ? { ok: true, csrfToken: 'csrf-value' } : { ok: true }),
  });
  await api.guardarToken('must-not-be-written-to-browser-storage');
  await api.restaurarToken();
  assert.equal(api.rutaAuth('login'), 'login/');
  assert.equal(api.rutaAuth('verificar'), 'verificar/');
  await api.peticionSistema('login/', { metodo: 'POST', datos: { usuario: 'admin' } });
  await api.peticionSistema('resenas/id/decision/', { metodo: 'POST', datos: { decision: 'aprobar' } });
  assert.equal(requests.length, 3);
  assert.ok(requests[0].url.endsWith('/csrf/'));
  assert.equal(requests[0].method, 'GET');
  for (const request of requests) {
    assert.equal(request.credentials, 'include');
    assert.equal(request.headers.Authorization, undefined);
  }
  assert.equal(requests[1].headers['X-CSRFToken'], 'csrf-value');
  assert.equal(requests[2].headers['X-CSRFToken'], 'csrf-value');
  assert.equal(storageCalls.length, 0);
});

test('web verification and logout invalidate the cached CSRF token', async () => {
  const { api, requests } = loadApi({
    platform: 'web',
    fetch: async url => reply(url.endsWith('/csrf/') ? { ok: true, csrfToken: 'csrf-value' } : { ok: true }),
  });
  await api.peticionSistema('verificar/', { metodo: 'POST', datos: { codigo: '123456' } });
  await api.peticionSistema('salir/', { metodo: 'POST' });
  await api.peticionSistema('login/', { metodo: 'POST', datos: { usuario: 'admin' } });
  assert.equal(requests.filter(request => request.url.endsWith('/csrf/')).length, 3);
});

test('a current-session 401 triggers expiry, while authentication failures preserve the session', async () => {
  const { api } = loadApi({ fetch: async () => reply({ ok: false, mensaje: 'Sesión inválida.' }, 401) });
  await api.guardarToken('current-token');
  let expired = 0;
  const stop = api.escucharSesionExpirada(() => { expired++; });
  for (const route of ['login/', 'verificar/', 'movil/login/', 'movil/verificar/']) {
    await assert.rejects(api.peticionSistema(route), error => error instanceof api.ApiError && error.status === 401);
  }
  assert.equal(expired, 0);
  await assert.rejects(api.peticionSistema('yo/'), error => error instanceof api.ApiError && error.status === 401);
  assert.equal(expired, 1);
  stop();
  await assert.rejects(api.peticionSistema('yo/'));
  assert.equal(expired, 1);
});

test('a late 401 for an old token cannot expire a newer native session', async () => {
  const pending = deferred();
  const { api, requests, setFetch, storage } = loadApi({ fetch: () => pending.promise });
  await api.guardarToken('old-token');
  let expired = 0;
  api.escucharSesionExpirada(() => { expired++; void api.guardarToken(null); });
  const oldRequest = api.peticionSistema('dashboard-crm/');
  await api.guardarToken('new-token');
  pending.resolve(reply({ ok: false, mensaje: 'Sesión anterior revocada.' }, 401));
  await assert.rejects(oldRequest, error => error instanceof api.ApiError && error.status === 401);
  assert.equal(expired, 0);
  assert.equal(storage.get('meg.sistema.sesion'), 'new-token');
  setFetch(async () => reply({ ok: true, usuario: { id: 1 } }));
  await api.peticionSistema('yo/');
  assert.equal(requests[0].headers.Authorization, 'Bearer old-token');
  assert.equal(requests[1].headers.Authorization, 'Bearer new-token');
});

test('an unauthorized response expires the current session even when its body is not JSON', async () => {
  const { api } = loadApi({ fetch: async () => ({ status: 401, ok: false, json: async () => { throw new SyntaxError('html'); } }) });
  await api.guardarToken('current-token');
  let expired = 0;
  api.escucharSesionExpirada(() => { expired++; });
  await assert.rejects(api.peticionSistema('yo/'), error => error instanceof api.ApiError && error.status === 401);
  assert.equal(expired, 1);
});

test('permission errors preserve sessions and expose the server message', async () => {
  const { api } = loadApi({ fetch: async () => reply({ ok: false, mensaje: 'Solo administradores.' }, 403) });
  await api.guardarToken('collaborator-token');
  let expired = 0;
  api.escucharSesionExpirada(() => { expired++; });
  await assert.rejects(api.peticionSistema('finanzas/dashboard/'), error => error.status === 403 && error.message === 'Solo administradores.');
  assert.equal(expired, 0);
  assert.equal(api.hayToken(), true);
});

test('transport failures become readable API errors and clean their timeout', async () => {
  const { api, timers } = loadApi({ fetch: async () => { throw new TypeError('network down'); } });
  await assert.rejects(api.peticionSistema('yo/'), error => error instanceof api.ApiError && error.status === 0 && /conectar/.test(error.message));
  assert.equal(timers.size, 0);
});

test('requests time out after 20 seconds without waiting in the test', async () => {
  const { api, timers } = loadApi({
    fetch: (_url, { signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
    }),
  });
  const pending = api.peticionSistema('yo/');
  assert.equal(timers.size, 1);
  const timeout = [...timers.values()][0];
  assert.equal(timeout.ms, 20000);
  timeout.callback();
  await assert.rejects(pending, error => error instanceof api.ApiError && error.status === 0 && /tardó demasiado/.test(error.message));
  assert.equal(timers.size, 0);
});

test('caller cancellation stays distinguishable from network and timeout errors', async () => {
  const aborted = new Error('screen unmounted');
  const controller = new AbortController();
  const { api, timers } = loadApi({
    fetch: (_url, { signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(aborted), { once: true });
    }),
  });
  const pending = api.peticionSistema('yo/', { signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, error => error === aborted);
  assert.equal(timers.size, 0);
});

test('missing or invalid API configuration never sends a request', async () => {
  for (const options of [{ url: '' }, { url: 'postgresql://private' }, { url: 'http://api.example.test', dev: false }]) {
    const { api, requests } = loadApi(options);
    await assert.rejects(api.peticionSistema('yo/'), error => error instanceof api.ApiError && error.status === 0);
    assert.equal(requests.length, 0);
  }
});

test('non-JSON server failures report a useful configuration error', async () => {
  const { api } = loadApi({ fetch: async () => ({ status: 502, ok: false, json: async () => { throw new SyntaxError('html'); } }) });
  await assert.rejects(api.peticionSistema('yo/'), error => error.status === 502 && /JSON/.test(error.message));
});

test('an application-level rejection is not mistaken for a successful save', async () => {
  const { api } = loadApi({ fetch: async () => reply({ ok: false, mensaje: 'No se pudo guardar.' }) });
  await assert.rejects(api.peticionSistema('oferta-valor/prospectos/', { metodo: 'POST', datos: {} }),
    error => error instanceof api.ApiError && error.message === 'No se pudo guardar.');
});

test('a slow deletion is ordered before saving the next native session', async () => {
  const deletion = deferred();
  let onDelete;
  const started = new Promise(resolve => { onDelete = resolve; });
  const calls = [];
  let persisted = null;
  const { api } = loadApi({ secureStore: {
    async setItemAsync(_key, value) { calls.push(['set', value]); persisted = value; },
    async deleteItemAsync() { calls.push(['delete']); onDelete(); await deletion.promise; persisted = null; },
  } });
  await api.guardarToken('old-token');
  const remove = api.guardarToken(null);
  const replace = api.guardarToken('new-token');
  await started;
  assert.equal(api.hayToken(), true);
  assert.deepEqual(calls, [['set', 'old-token'], ['delete']]);
  deletion.resolve();
  await Promise.all([remove, replace]);
  assert.deepEqual(calls, [['set', 'old-token'], ['delete'], ['set', 'new-token']]);
  assert.equal(persisted, 'new-token');
});

test('SecureStore write failures restore the prior in-memory token', async () => {
  let fail = false;
  const { api, requests } = loadApi({ secureStore: {
    async setItemAsync() { if (fail) throw new Error('secure storage unavailable'); },
  } });
  await api.guardarToken('previous-token');
  fail = true;
  await assert.rejects(api.guardarToken('failed-token'), /secure storage unavailable/);
  await api.peticionSistema('yo/');
  assert.equal(requests[0].headers.Authorization, 'Bearer previous-token');
});
