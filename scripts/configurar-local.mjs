import { networkInterfaces } from 'node:os';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

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
let previous = '';
try { previous = readFileSync(path, 'utf8'); } catch (error) { if (error.code !== 'ENOENT') throw error; }
const line = `EXPO_PUBLIC_API_URL=http://${address}:8000`;
const content = /^EXPO_PUBLIC_API_URL=.*$/m.test(previous) ? previous.replace(/^EXPO_PUBLIC_API_URL=.*$/m, line) : `${previous}${previous && !previous.endsWith('\n') ? '\n' : ''}${line}\n`;
writeFileSync(path, content);
console.log(`App configurada: http://${address}:8000`);
console.log(`Incluye ${address} en ALLOWED_HOSTS del .env de Django.`);
console.log('Ejecuta Django con runserver 0.0.0.0:8000 y reinicia Expo.');
