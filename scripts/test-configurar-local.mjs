import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import test from 'node:test';

function project(t, { frontend = '', backend } = {}) {
  const prefix = join(tmpdir(), 'meg-configurar-local-');
  const root = mkdtempSync(prefix);
  t.after(() => {
    const target = resolve(root);
    assert.ok(target.startsWith(resolve(prefix)) && target.startsWith(resolve(tmpdir()) + sep));
    rmSync(target, { recursive: true, force: true });
  });
  mkdirSync(join(root, 'scripts'));
  mkdirSync(join(root, 'backend', 'servidor'), { recursive: true });
  const script = join(root, 'scripts', 'configurar-local.mjs');
  const frontendPath = join(root, '.env');
  const backendPath = join(root, 'backend', 'servidor', '.env');
  copyFileSync(new URL('./configurar-local.mjs', import.meta.url), script);
  writeFileSync(frontendPath, frontend);
  if (backend !== undefined) writeFileSync(backendPath, backend);
  return {
    run: address => execFileSync(process.execPath, [script, address], { encoding: 'utf8', stdio: 'pipe' }),
    frontend: () => readFileSync(frontendPath, 'utf8'),
    backend: () => readFileSync(backendPath, 'utf8'),
    hasBackend: () => existsSync(backendPath),
  };
}

test('configuración local conserva secretos, formato, comentarios y orígenes existentes', t => {
  const files = project(t, {
    frontend: '# App\r\nEXPO_PUBLIC_API_URL="http://192.168.1.77:8000" # IP anterior\r\nOTRA_VARIABLE=valor\r\n',
    backend: [
      '# Servidor privado',
      "DEBUG='True' # solo local",
      "SECRET_KEY='secreto#con=comillas'",
      'NEON_DATABASE_URL="postgresql://usuario:clave@ejemplo/base?sslmode=require"',
      "ALLOWED_HOSTS='api.example.test,localhost' # hosts",
      ' export CORS_ALLOWED_ORIGINS = "https://example.test" # web',
      '',
    ].join('\r\n'),
  });
  const output = files.run('192.168.16.168');
  const frontend = files.frontend();
  const backend = files.backend();
  assert.match(frontend, /EXPO_PUBLIC_API_URL="http:\/\/192\.168\.16\.168:8000" # IP anterior\r\n/);
  assert.match(frontend, /EXPO_PUBLIC_API_URL_WEB=http:\/\/localhost:8000\r\n/);
  assert.match(frontend, /EXPO_PUBLIC_API_URL_ANDROID=http:\/\/10\.0\.2\.2:8000\r\n/);
  assert.match(frontend, /OTRA_VARIABLE=valor\r\n/);
  assert.match(backend, /SECRET_KEY='secreto#con=comillas'\r\n/);
  assert.match(backend, /NEON_DATABASE_URL="postgresql:\/\/usuario:clave@ejemplo\/base\?sslmode=require"\r\n/);
  assert.match(backend, /ALLOWED_HOSTS='api\.example\.test,localhost,127\.0\.0\.1,10\.0\.2\.2,192\.168\.16\.168' # hosts\r\n/);
  assert.match(backend, / export CORS_ALLOWED_ORIGINS = "https:\/\/example\.test,http:\/\/localhost:8081,http:\/\/localhost:8090,http:\/\/127\.0\.0\.1:8081,http:\/\/127\.0\.0\.1:8090,http:\/\/192\.168\.16\.168:8081,http:\/\/192\.168\.16\.168:8090" # web\r\n/);
  assert.doesNotMatch(output, /secreto|postgresql/);
  files.run('192.168.16.168');
  assert.equal(files.frontend(), frontend);
  assert.equal(files.backend(), backend);
});

test('configuración local acepta hosts y orígenes vacíos', t => {
  const files = project(t, { backend: 'DEBUG = True # local\nALLOWED_HOSTS= # vacío\nCORS_ALLOWED_ORIGINS=""\n' });
  files.run('192.168.16.168');
  assert.match(files.backend(), /ALLOWED_HOSTS= localhost,127\.0\.0\.1,10\.0\.2\.2,192\.168\.16\.168 # vacío/);
  assert.match(files.backend(), /CORS_ALLOWED_ORIGINS="http:\/\/localhost:8081/);
});

test('no cambia configuración de producción ni crea el archivo privado que falta', t => {
  for (const debug of ['False', '']) {
    const original = `DEBUG=${debug}\nSECRET_KEY=conservar\nALLOWED_HOSTS=api.example.test\n`;
    const files = project(t, { backend: original });
    files.run('192.168.16.168');
    assert.equal(files.backend(), original);
  }
  const missing = project(t);
  missing.run('192.168.16.168');
  assert.equal(missing.hasBackend(), false);
});

test('una IP inválida no modifica los archivos', t => {
  const files = project(t, { frontend: 'EXPO_PUBLIC_API_URL=https://api.example.test\n', backend: 'DEBUG=True\n' });
  assert.throws(() => files.run('192.168.1.999'));
  assert.equal(files.frontend(), 'EXPO_PUBLIC_API_URL=https://api.example.test\n');
  assert.equal(files.backend(), 'DEBUG=True\n');
});
