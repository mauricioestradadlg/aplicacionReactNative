import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { request } from 'node:http';
import { isIP } from 'node:net';
import { delimiter, join, resolve } from 'node:path';

function fail(message) {
  console.error(message);
  process.exit(1);
}

const args = process.argv.slice(2);
const flags = new Map();
for (let index = 0; index < args.length; index += 2) {
  const [flag, value] = args.slice(index, index + 2);
  if (!['--serial', '--package'].includes(flag) || !value || value.startsWith('--') || flags.has(flag)) {
    fail('Uso: node scripts/diagnosticar-android.mjs [--serial SERIAL] [--package PAQUETE_ANDROID]');
  }
  flags.set(flag, value);
}
const requestedSerial = flags.get('--serial');
const packageName = flags.get('--package') || 'host.exp.exponent';
if (!/^[a-zA-Z][\w]*(?:\.[a-zA-Z][\w]*)+$/.test(packageName)) fail('El paquete Android no es válido. Ejemplo: --package com.empresa.aplicacion');

const env = {};
try {
  const content = readFileSync(resolve(import.meta.dirname, '..', '.env'), 'utf8');
  for (const line of content.split(/\r?\n/)) {
    const match = line.match(/^\s*(?:export\s+)?(EXPO_PUBLIC_API_URL(?:_ANDROID)?)\s*=\s*(.*?)\s*$/);
    if (!match) continue;
    const quoted = match[2].match(/^(['"])(.*?)\1\s*(?:#.*)?$/);
    env[match[1]] = quoted ? quoted[2] : match[2].replace(/\s*#.*$/, '').trim();
  }
} catch (error) {
  if (error.code !== 'ENOENT') fail('No se pudo leer .env. Revisa los permisos del archivo.');
}
const configured = { ...env, ...process.env };
const value = configured.EXPO_PUBLIC_API_URL_ANDROID?.trim() || configured.EXPO_PUBLIC_API_URL?.trim();
if (!value) fail('Configura EXPO_PUBLIC_API_URL_ANDROID o EXPO_PUBLIC_API_URL en .env antes de comprobar Android.');
let target;
try { target = new URL(value); }
catch { fail('La dirección del backend no es una URL válida. Usa http://HOST:PUERTO sin /api al final.'); }
if (target.protocol === 'https:') {
  fail('Este diagnóstico con nc solo admite HTTP local. Para HTTPS, abre la dirección del backend en el navegador del emulador.');
}
if (target.protocol !== 'http:' || target.username || target.password || target.pathname !== '/' || target.search || target.hash) {
  fail('Usa el origen HTTP local del backend, sin credenciales, /api, parámetros ni fragmentos.');
}
const hostname = target.hostname.replace(/^\[|\]$/g, '');
if (!isIP(hostname) && !/^(?:[a-z\d](?:[a-z\d-]*[a-z\d])?\.)*[a-z\d](?:[a-z\d-]*[a-z\d])?$/i.test(hostname)) {
  fail('El nombre del servidor no es válido para el diagnóstico.');
}
const port = target.port || '80';
if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535) fail('El puerto del backend no es válido.');

const checks = [
  { method: 'GET', path: '/api/sistema/app/csrf/', expected: 200 },
  { method: 'GET', path: '/api/sistema/app/yo/', expected: 401 },
];
// 10.0.2.2 identifica a la PC únicamente dentro de Android Emulator.
// Conservar Host permite detectar también ALLOWED_HOSTS incorrecto en Django.
const pcTarget = new URL(target);
if (hostname === '10.0.2.2') pcTarget.hostname = '127.0.0.1';
for (const check of checks) {
  const started = Date.now();
  let status;
  try {
    status = await new Promise((resolveStatus, reject) => {
      const connection = request(new URL(check.path, pcTarget), {
        method: check.method,
        headers: { Host: target.host, Accept: 'application/json' },
        signal: AbortSignal.timeout(5000),
      }, response => {
        response.resume(); // Descartar cuerpos: csrf/ contiene un token de navegador.
        resolveStatus(response.statusCode);
      });
      connection.on('error', reject);
      connection.end();
    });
  } catch (error) {
    const reason = error.code === 'ECONNREFUSED' ? 'conexión rechazada'
      : error.code === 'ABORT_ERR' ? 'tiempo agotado' : 'error de conexión';
    fail(`Django no responde desde esta PC en ${pcTarget.origin} (${reason}). Inicia el backend con python backend/servidor/manage.py runserver 0.0.0.0:${port} y comprueba la dirección configurada. Expo y Django son servidores independientes.`);
  }
  console.log(`PC: ${check.method} ${pcTarget.origin}${check.path}: HTTP ${status} (esperado ${check.expected}), ${Date.now() - started} ms`);
  if (status !== check.expected) {
    const hint = status === 400 ? `Incluye ${hostname} en ALLOWED_HOSTS de Django.`
      : status === 404 ? 'La URL apunta a un backend que no tiene las rutas /api/sistema/app/.'
      : status === 503 ? 'Revisa la conexión de NEON_MOBILE_DATABASE_URL y la instalación de la base móvil.'
      : 'Revisa los registros de Django y la configuración del backend.';
    fail(`El backend responde desde la PC, pero devolvió HTTP ${status}. ${hint}`);
  }
}

const adbName = process.platform === 'win32' ? 'adb.exe' : 'adb';
const sdkRoots = [process.env.ANDROID_HOME, process.env.ANDROID_SDK_ROOT,
  process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, 'Android', 'Sdk')].filter(Boolean);
const candidates = [
  ...sdkRoots.map(root => join(root, 'platform-tools', adbName)),
  ...(process.env.PATH || process.env.Path || '').split(delimiter).filter(Boolean)
    .map(directory => join(directory.replace(/^"|"$/g, ''), adbName)),
];
const adb = candidates.find(candidate => existsSync(candidate));
if (!adb) fail('El backend responde desde la PC. No se encontró adb para comprobar Android. Instala Android SDK Platform-Tools o configura ANDROID_HOME, ANDROID_SDK_ROOT o PATH.');
if (hostname === '10.0.2.2') console.log('10.0.2.2 es exclusiva de Android Emulator. En un teléfono físico usa la IP LAN de la PC.');

const listing = spawnSync(adb, ['devices'], { encoding: 'utf8', timeout: 5000, windowsHide: true });
if (listing.error || listing.status !== 0) fail('No se pudo consultar adb. Abre Android Studio y comprueba que el emulador esté iniciado.');
const devices = listing.stdout.split(/\r?\n/).map(line => line.match(/^(\S+)\s+(device|offline|unauthorized)\b/))
  .filter(Boolean).map(match => ({ serial: match[1], state: match[2] }));
const ready = devices.filter(device => device.state === 'device');
const selected = requestedSerial ? ready.find(device => device.serial === requestedSerial) : ready.length === 1 ? ready[0] : undefined;
if (!selected) {
  const available = devices.map(device => `${device.serial} (${device.state})`).join(', ') || 'ninguno';
  fail(`No hay un único dispositivo listo${requestedSerial ? ` con serial ${requestedSerial}` : ''}. Dispositivos: ${available}. Inicia o autoriza Android; si hay varios, usa --serial SERIAL.`);
}

console.log('Las consultas con nc usan el usuario shell de adb; pueden funcionar aunque la app no tenga permiso de red local.');
const inspectAndroid = commands => spawnSync(adb, ['-s', selected.serial, 'shell', ...commands], {
  encoding: 'utf8', timeout: 5000, maxBuffer: 2 * 1024 * 1024, windowsHide: true,
});
const version = inspectAndroid(['getprop', 'ro.build.version.sdk']);
const sdk = Number(version.stdout?.trim());
if (version.error || version.status !== 0 || !Number.isInteger(sdk) || sdk < 1) {
  console.warn('No se pudo comprobar la versión de Android ni el permiso de red local de la app.');
} else if (sdk >= 37) {
  const info = inspectAndroid(['dumpsys', 'package', packageName]);
  const targetSdk = Number(info.stdout?.match(/\btargetSdk=(\d+)\b/)?.[1]);
  const permission = info.stdout?.match(/android\.permission\.ACCESS_LOCAL_NETWORK:\s*granted=(true|false)\b/)?.[1];
  if (info.error || info.status !== 0 || !Number.isInteger(targetSdk)) {
    console.warn(`No se pudo comprobar el permiso de ${packageName}. Para una compilación propia indica --package con su identificador Android.`);
  } else if (permission === 'false') {
    const label = packageName === 'host.exp.exponent' ? 'Expo Go' : packageName;
    fail(`Android bloquea la red local de ${label}: ACCESS_LOCAL_NETWORK está denegado. La denegación explícita puede bloquear conexiones también con targetSdk anterior a 37 por ajustes de compatibilidad. Abre Ajustes > Apps > ${label} > Permisos > Dispositivos cercanos / Red local y permite el acceso; después recarga la app. Un HTTP 200 obtenido con adb/nc no comprueba este permiso. No se modificaron permisos.`);
  } else if (targetSdk >= 37 && permission !== 'true') {
    fail(`${packageName} no tiene un permiso ACCESS_LOCAL_NETWORK concedido verificable. Declara y solicita el permiso de red local en la app para Android 17; en una compilación propia será necesario reconstruirla. No se modificaron permisos.`);
  } else if (permission === 'true') {
    console.log(`Permiso de red local de ${packageName}: concedido.`);
  }
}

// El payload base64 evita interpretar sus saltos de línea en el shell remoto.
// Solo se envían consultas sin credenciales; no se escriben datos ni límites.
const quote = value => `'${value.replace(/'/g, "'\\''")}'`;
let failed = false;
for (const check of checks) {
  const headers = [`${check.method} ${check.path} HTTP/1.1`, `Host: ${target.host}`, 'Accept: application/json', 'Connection: close'];
  const payload = Buffer.from(headers.join('\r\n') + '\r\n\r\n').toString('base64');
  const command = `printf %s ${quote(payload)} | base64 -d | nc -w 5 ${quote(hostname)} ${quote(port)}`;
  const started = Date.now();
  const response = spawnSync(adb, ['-s', selected.serial, 'shell', command], {
    encoding: 'utf8', timeout: 8000, maxBuffer: 1024 * 1024, windowsHide: true,
  });
  const elapsed = Date.now() - started;
  const status = response.stdout?.match(/^HTTP\/\d(?:\.\d)?\s+(\d{3})\b/m)?.[1];
  const success = Number(status) === check.expected;
  if (!success) failed = true;
  // No mostrar cuerpos ni cabeceras: csrf/ contiene un token de navegador.
  console.log(`${check.method} ${target.origin}${check.path}: ${status ? `HTTP ${status}` : 'sin respuesta HTTP'} (esperado ${check.expected}), ${elapsed} ms`);
  if (Number(status) === 503) console.error('El backend responde, pero la base móvil no está disponible. Revisa la conexión de NEON_MOBILE_DATABASE_URL y la instalación de la base móvil.');
  if (!status) console.error('Comprueba que Django esté encendido, la dirección sea accesible desde Android y el dispositivo disponga de nc/base64.');
}
process.exitCode = failed ? 1 : 0;
