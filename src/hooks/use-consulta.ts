import { useCallback, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';
import { peticionSistema } from '@/services/api';

export function useConsulta<T>(ruta: string | null) {
  const [result, setResult] = useState<{ ruta: string | null; datos: T | null }>({ ruta, datos: null });
  const [cargando, setCargando] = useState(Boolean(ruta));
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  const recargar = useCallback(async () => {
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    if (!ruta) { setResult({ ruta, datos: null }); setCargando(false); setError(''); return; }
    setCargando(true);
    setError('');
    try {
      const result = await peticionSistema<T>(ruta, { signal: request.signal });
      if (!request.signal.aborted) setResult({ ruta, datos: result });
    } catch (err) {
      if (!request.signal.aborted) { setResult({ ruta, datos: null }); setError(err instanceof Error ? err.message : 'No se pudo consultar la información.'); }
    } finally { if (!request.signal.aborted) setCargando(false); }
  }, [ruta]);
  useFocusEffect(useCallback(() => { void recargar(); return () => controller.current?.abort(); }, [recargar]));
  const vigente = result.ruta === ruta;
  return { datos: vigente ? result.datos : null, cargando: vigente ? cargando : Boolean(ruta), error: vigente ? error : '', recargar };
}
