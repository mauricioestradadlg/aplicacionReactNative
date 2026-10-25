import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

export const API_URL = (process.env.EXPO_PUBLIC_API_URL || '').trim().replace(/\/+$/, '');
const TOKEN_KEY = 'meg.sistema.sesion';
let token: string | null = null;
let csrf: string | null = null;
let onUnauthorized: (() => void) | undefined;
let storageQueue = Promise.resolve();

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); }
}

export function escucharSesionExpirada(listener: () => void) {
  onUnauthorized = listener;
  return () => { if (onUnauthorized === listener) onUnauthorized = undefined; };
}

export async function restaurarToken() {
  if (Platform.OS !== 'web') token = await SecureStore.getItemAsync(TOKEN_KEY);
}

export async function guardarToken(value: string | null) {
  const previous = token;
  token = value;
  csrf = null;
  const task = storageQueue.then(async () => {
    if (Platform.OS !== 'web') {
      if (value) await SecureStore.setItemAsync(TOKEN_KEY, value);
      else await SecureStore.deleteItemAsync(TOKEN_KEY);
    }
  });
  storageQueue = task.catch(() => {});
  try { await task; }
  catch (error) { if (token === value) token = previous; throw error; }
}

export function hayToken() { return Platform.OS === 'web' || Boolean(token); }

type Options = { metodo?: string; datos?: unknown; signal?: AbortSignal };

export async function peticionSistema<T = Record<string, unknown>>(ruta: string, options: Options = {}): Promise<T> {
  if (!API_URL) throw new ApiError('Configura EXPO_PUBLIC_API_URL en .env con la dirección de tu backend y reinicia Expo.', 0);
  if (!/^https?:\/\//i.test(API_URL)) throw new ApiError('La dirección del backend debe empezar con https:// o http://.', 0);
  if (!__DEV__ && !API_URL.startsWith('https://')) throw new ApiError('La conexión al sistema requiere HTTPS en producción.', 0);
  const method = (options.metodo || 'GET').toUpperCase();
  const requestToken = token;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.datos !== undefined) headers['Content-Type'] = 'application/json';
  if (Platform.OS !== 'web' && requestToken) headers.Authorization = `Bearer ${requestToken}`;
  if (Platform.OS === 'web' && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    if (!csrf) {
      const result = await peticionSistema<{ csrfToken: string }>('csrf/', { signal: options.signal });
      if (!result.csrfToken) throw new ApiError('No se pudo preparar la protección de la sesión.', 403);
      csrf = result.csrfToken;
    }
    headers['X-CSRFToken'] = csrf;
  }
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  options.signal?.addEventListener('abort', abort);
  const timeout = setTimeout(abort, 20000);
  try {
    const response = await fetch(`${API_URL}/api/sistema/${ruta}`, {
      method, headers, signal: controller.signal,
      body: options.datos === undefined ? undefined : JSON.stringify(options.datos),
      credentials: Platform.OS === 'web' ? 'include' : 'omit',
      cache: 'no-store',
    });
    if (response.status === 401 && !/^(movil\/)?(login|verificar)\//.test(ruta) && (Platform.OS === 'web' || requestToken === token)) onUnauthorized?.();
    const body: unknown = await response.json().catch(() => null);
    if (!body || typeof body !== 'object') throw new ApiError('El servidor no devolvió JSON. Revisa la URL y la configuración del backend.', response.status);
    const result = body as { ok?: boolean; mensaje?: string };
    if (!response.ok || result.ok === false) {
      throw new ApiError(result.mensaje || 'No se pudo completar la solicitud.', response.status);
    }
    if (ruta === 'salir/' || ruta === 'verificar/') csrf = null;
    return body as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (options.signal?.aborted) throw error;
    if (controller.signal.aborted) throw new ApiError('El servidor tardó demasiado. Intenta de nuevo.', 0);
    throw new ApiError('No fue posible conectar con el servidor. Revisa tu conexión y la dirección del backend.', 0);
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener('abort', abort);
  }
}

export const rutaAuth = (ruta: 'login' | 'verificar') => `${Platform.OS === 'web' ? '' : 'movil/'}${ruta}/`;
