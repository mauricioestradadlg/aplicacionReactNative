import { useState } from 'react';
import { Text, View } from 'react-native';

import { Button, Card, Chip, Stat, Toggle } from '@/components/meg';

import { Feedback, Identity, PagedList, Search, fecha, keyProspecto, servicio, styles, useMutation, usePage, type Prospecto, type ProspectosPage } from './common';

type SaleState = { cita_completada: boolean; cotizacion_enviada: boolean; hubo_venta: boolean };
const initialSale = (p: Prospecto): SaleState => ({ cita_completada: Boolean(p.cita_completada), cotizacion_enviada: Boolean(p.cotizacion_enviada), hubo_venta: Boolean(p.hubo_venta) });

function CloseCard({ person, busy, onSave }: { person: Prospecto; busy: boolean; onSave: (p: Prospecto, state: SaleState) => Promise<boolean> }) {
  const [draft, setDraft] = useState<SaleState | null>(null);
  const state = draft || initialSale(person);
  const fields = [['cita_completada', 'Cita completada'], ['cotizacion_enviada', 'Cotización enviada'], ['hubo_venta', 'Hubo venta']] as const;
  async function guardar() { if (await onSave(person, state)) setDraft(null); }
  return <Card><Identity person={person} /><View style={styles.row}><Chip label={person.origen || person.fuente} /><Chip label={servicio(person.servicio_recomendado)} /></View>
    <Text style={styles.muted}>Cita agendada: {fecha(person.cita_agendada_en)}</Text>
    {fields.map(([field, label]) => <Toggle key={field} label={label} value={state[field]} onValueChange={v => setDraft({ ...state, [field]: v })} disabled={busy} />)}
    <Button label={draft ? 'Guardar seguimiento' : 'Sin cambios pendientes'} onPress={() => void guardar()} disabled={!draft || busy} />
  </Card>;
}

export function CierreVentasScreen() {
  const page = usePage<ProspectosPage>('cierre-ventas/');
  const mutation = useMutation();
  async function guardar(p: Prospecto, state: SaleState) {
    if (state.hubo_venta && (!state.cita_completada || !state.cotizacion_enviada)) {
      mutation.setError('Para registrar una venta, confirma la cita completada y la cotización enviada.'); return false;
    }
    return mutation.mutate(keyProspecto(p), `cierre-ventas/${p.id}/estado/`, { fuente: p.fuente, ...state }, page.recargar);
  }
  return <PagedList title="Cierre de ventas" subtitle="De la primera cita a una venta confirmada." items={page.datos?.prospectos || []} keyExtractor={keyProspecto}
    renderItem={p => <CloseCard person={p} busy={Boolean(mutation.busy) || page.cargando} onSave={guardar} />}
    header={<><Search value={page.search} onChange={page.setSearch} onSearch={page.buscar} /><Feedback error={mutation.error} success={mutation.success} />
      {page.datos ? <View style={styles.row}><Stat label="Citas" value={String(page.datos.totales?.citas ?? 0)} /><Stat label="Cotizaciones" value={String(page.datos.totales?.cotizaciones ?? 0)} /><Stat label="Ventas" value={String(page.datos.totales?.ventas ?? 0)} /></View> : null}</>}
    loading={page.cargando} error={page.error} recargar={page.recargar} pagina={page.pagina} paginas={page.datos?.paginas || 0} setPagina={page.setPagina} isAdmin={page.isAdmin} scrollToTopKey={mutation.error || mutation.success} />;
}
