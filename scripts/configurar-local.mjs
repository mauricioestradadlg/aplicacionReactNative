import { networkInterfaces } from 'node:os';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

// Editar solo estas asignaciones conserva las credenciales y los comentarios.
const assignment = key => new RegExp(`^([ \\t]*(?:export[ \\t]+)?${key}[ \\t]*=[ \\t]*)(.*?)(\\r?)$`, 'gm');
const parts = raw => {
  const quoted = raw.match(/^(['"])(.*?)\1([ \t]*(?:#.*)?)$/);
  if (quoted) return { quote: quoted[1], value: quoted[2], suffix: quoted[3] };
  const unquoted = raw.match(/^(.*?)([ \t]*(?:#.*)?)$/);
  return { quote: '', value: unquoted[1], suffix: unquoted[2] };
};
const readValue = (content, key) => {
  const matches = [...content.matchAll(assignment(key))];
  return matches.length ? parts(matches.at(-1)[2]).value : '';
};
const setValue = (content, key, value) => {
  let found = false;
  const updated = content.replace(assignment(key), (_line, prefix, raw, cr) => {
    found = true;
    const { quote, suffix } = parts(raw);
    const comment = suffix.startsWith('#') ? ` ${suffix}` : suffix;
    return `${prefix}${quote}${value}${quote}${comment}${cr}`;
  });
  if (found) return updated;
  const newline = content.includes('\r\n') ? '\r\n' : '\n';
  return `${content}${content && !content.endsWith('\n') ? newline : ''}${key}=${value}${newline}`;
};
const addValues = (content, key, values) => setValue(content, key,
  [...new Set([...readValue(content, key).split(','), ...values].map(value => value.trim()).filter(Boolean))].join(','));
const readOptional = path => {
  try { return readFileSync(path, 'utf8'); }
  catch (error) { if (error.code !== 'ENOENT') throw error; return null; }
};

const privateIp = address => /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(address);
const candidates = Object.entries(networkInterfaces()).flatMap(([name, interfaces]) => (interfaces || [])
  .filter(info => info.family === 'IPv4' && !info.internal && privateIp(info.address))
  .map(info => ({ name, address: info.address })));
const explicit = process.argv[2];
const preferred = candidates.filter(item => /wi-?fi|wlan|ethernet/i.test(item.name) && !/virtual|vethernet|vpn/i.test(item.name));
const choices = preferred.length ? preferred : candidates;
const address = explicit || (choices.length === 1 ? choices[0].address : '');
if (!address || !/^(\d{1,3}\.){3}\d{1,3}$/.test(address) || address.split('.').some(n => Number(n) > 255)) {
  console.error('Indica la IP de tu computadora: npm run configurar:local -- 192.168.1.77');
  for (const item of candidates) console.error(`${item.name}: ${item.address}`);
  process.exit(1);
}
const path = resolve(import.meta.dirname, '..', '.env');
let content = readOptional(path) ?? '';
content = setValue(content, 'EXPO_PUBLIC_API_URL', `http://${address}:8000`);
content = setValue(content, 'EXPO_PUBLIC_API_URL_WEB', 'http://localhost:8000');
content = setValue(content, 'EXPO_PUBLIC_API_URL_ANDROID', 'http://10.0.2.2:8000');
writeFileSync(path, content);
console.log(`Teléfono físico: http://${address}:8000`);
console.log('Navegador: http://localhost:8000 · Android Emulator: http://10.0.2.2:8000');

const backendPath = resolve(import.meta.dirname, '..', 'backend', 'servidor', '.env');
let backend = readOptional(backendPath);
if (backend === null) {
  console.warn('Falta backend/servidor/.env. Configura Django antes de iniciar sesión.');
} else if (readValue(backend, 'DEBUG').trim().toLowerCase() !== 'true') {
  console.warn('No se modificó backend/servidor/.env: la sincronización local requiere DEBUG=True.');
} else {
  const hosts = ['localhost', '127.0.0.1', '10.0.2.2', address];
  const origins = ['localhost', '127.0.0.1', address]
    .flatMap(host => [8081, 8090].map(port => `http://${host}:${port}`));
  backend = addValues(backend, 'ALLOWED_HOSTS', hosts);
  backend = addValues(backend, 'CORS_ALLOWED_ORIGINS', origins);
  writeFileSync(backendPath, backend);
  console.log('Hosts y orígenes locales de Django actualizados.');
}
console.log('Ejecuta Django con runserver 0.0.0.0:8000 y reinicia Expo.');
