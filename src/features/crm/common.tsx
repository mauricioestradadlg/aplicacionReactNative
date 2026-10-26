import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ActivityIndicator, FlatList, StyleSheet, Text, View } from 'react-native';

import { Button, Card, Empty, Field, Notice, Pagination, Screen, colors } from '@/components/meg';
import { useSession } from '@/context/session';
import { useConsulta } from '@/hooks/use-consulta';
import { peticionSistema } from '@/services/api';
import { puedeAcceder } from '@/services/access';

export type Page = { pagina: number; paginas: number; total: number; totales?: Record<string, number> };
export type Prospecto = {
  id: string; fuente: string; nombre: string; telefono: string; negocio: string;
  servicio_recomendado: string; origen: string; fecha_registro?: string;
  respondio_mensajes?: boolean; brindo_nombre?: boolean; cita_agendada_en?: string | null;
  cita_completada?: boolean; cotizacion_enviada?: boolean; hubo_venta?: boolean;
  proyecto_liquidado?: boolean; importe_total?: string | null; importe_anticipo?: string | null;
  fecha_anticipo?: string | null; fecha_liquidacion?: string | null;
};
export type Lead = {
  id: string; nombre: string; correo: string; whatsapp: string; negocio: string; plantilla: string;
  acepto_privacidad?: boolean; acepto_correos?: boolean; fecha_registro?: string;
  tips_enviados_en?: string | null; feedback_enviado_en?: string | null; oportunidad_comercial_en?: string | null;
};
export type ProspectosPage = Page & { prospectos: Prospecto[] };
export type LeadsPage = Page & { leads: Lead[] };

export function fecha(value?: string | null) {
  if (!value) return 'Sin registrar';
  const date = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  return Number.isNaN(date.getTime()) ? 'Sin registrar' : new Intl.DateTimeFormat('es-MX', {
    dateStyle: 'medium', ...(value.length > 10 ? { timeStyle: 'short' as const } : {}),
  }).format(date);
}
export const money = (value: number | string | null | undefined) => new Intl.NumberFormat('es-MX', {
  style: 'currency', currency: 'MXN',
}).format(Number(value) || 0);
export const keyProspecto = (p: Prospecto) => `${p.fuente}:${p.id}`;
export const servicio = (s: string) => ({ 'landing-page': 'Landing Page', 'sitio-web': 'Sitio Web', 'diseno-web': 'Diseño Web', otro: 'Otro' })[s] || s || 'Sin definir';
export const errorMessage = (e: unknown) => e instanceof Error ? e.message : 'No se pudo completar la solicitud.';

export function useMutation() {
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  async function mutate(key: string, ruta: string, datos: unknown, after?: () => void | Promise<void>) {
    if (busy) return false;
    setBusy(key); setError(''); setSuccess('');
    try {
      await peticionSistema(ruta, { metodo: 'POST', datos });
      await after?.();
      setSuccess('Cambios guardados correctamente.');
      return true;
    } catch (e) { setError(errorMessage(e)); return false; }
    finally { setBusy(''); }
  }
  return { busy, error, success, setError, mutate };
}

export function usePage<T>(path: string) {
  const { usuario } = useSession();
  const [pagina, setPagina] = useState(1);
  const [search, setSearch] = useState('');
  const [filtro, setFiltro] = useState('');
  const [extra, setExtra] = useState('');
  const permitido = puedeAcceder(usuario, path === 'gestion-ventas/' ? 'finanzas' : 'crm');
  const query = useConsulta<T>(permitido ? `${path}?pagina=${pagina}&buscar=${encodeURIComponent(filtro)}${extra}` : null);
  function buscar() { setPagina(1); setFiltro(search.trim().slice(0, 100)); }
  return { ...query, pagina, setPagina, search, setSearch, buscar, setExtra, isAdmin: permitido };
}

export function Feedback({ error, success }: { error?: string; success?: string }) {
  return <>{error ? <Notice message={error} tone="error" /> : null}{success ? <Notice message={success} tone="success" /> : null}</>;
}

export function Identity({ person }: { person: { nombre: string; negocio: string; telefono?: string; correo?: string; whatsapp?: string } }) {
  return <View style={styles.identity}><Text style={styles.name}>{person.nombre || 'Sin nombre'}</Text>
    {person.negocio && person.negocio !== person.nombre ? <Text style={styles.body}>{person.negocio}</Text> : null}
    <Text selectable style={styles.muted}>{person.telefono || person.whatsapp || person.correo || 'Sin contacto'}</Text>
    {person.correo && (person.telefono || person.whatsapp) ? <Text selectable style={styles.muted}>{person.correo}</Text> : null}
  </View>;
}

export function Search({ value, onChange, onSearch }: { value: string; onChange: (s: string) => void; onSearch: () => void }) {
  return <Card><Field label="Buscar por nombre, correo o teléfono" placeholder="Escribe tu búsqueda" value={value} onChangeText={onChange} maxLength={100} returnKeyType="search" onSubmitEditing={onSearch} />
    <Button label="Buscar" onPress={onSearch} variant="secondary" /></Card>;
}

export function PagedList<T>({ title, subtitle, items, keyExtractor, renderItem, header, loading, error, refreshing, recargar, pagina, paginas, setPagina, isAdmin, scrollToTopKey }: {
  title: string; subtitle?: string; items: T[]; keyExtractor: (item: T) => string; renderItem: (item: T) => ReactNode;
  header?: ReactNode; loading: boolean; error?: string; refreshing?: boolean; recargar: () => Promise<void>;
  pagina: number; paginas: number; setPagina: (n: number) => void; isAdmin: boolean; scrollToTopKey?: string;
}) {
  const list = useRef<FlatList<T>>(null);
  useEffect(() => { if (scrollToTopKey) list.current?.scrollToOffset({ offset: 0, animated: true }); }, [scrollToTopKey]);
  return <Screen title={title} subtitle={subtitle} scroll={false}>
    {!isAdmin ? <Notice message="Tu cuenta no tiene acceso a esta sección." tone="info" /> : <FlatList ref={list}
      style={{ flex: 1 }} data={items} keyExtractor={keyExtractor} renderItem={({ item }) => <View style={styles.item}>{renderItem(item)}</View>}
      contentContainerStyle={styles.list} keyboardShouldPersistTaps="handled" refreshing={Boolean(refreshing || loading)} onRefresh={() => void recargar()}
      ListHeaderComponent={<View style={styles.header}>{header}{error ? <Notice message={error} tone="error" /> : null}
        {error ? <Button label="Reintentar" onPress={() => void recargar()} variant="secondary" /> : null}</View>}
      ListEmptyComponent={loading ? <ActivityIndicator color={colors.primary} style={{ padding: 28 }} /> : error ? <></> : <Empty message="No hay registros para estos filtros." />}
      ListFooterComponent={<Pagination pagina={pagina} paginas={paginas} onChange={setPagina} />}
      initialNumToRender={6} windowSize={5} />}
  </Screen>;
}

export const styles = StyleSheet.create({
  list: { paddingBottom: 28 }, item: { marginBottom: 12 }, header: { gap: 12, marginBottom: 12 },
  identity: { gap: 5 }, name: { color: colors.ink, fontSize: 18, fontWeight: '700' },
  body: { color: colors.ink, fontSize: 14, lineHeight: 22 }, muted: { color: colors.muted, fontSize: 13, lineHeight: 20 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' },
  heading: { color: colors.ink, fontSize: 17, fontWeight: '700', marginTop: 4 },
  separator: { height: 1, backgroundColor: colors.border, marginVertical: 5 },
});
