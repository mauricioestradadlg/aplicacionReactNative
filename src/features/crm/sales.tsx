import { useState } from 'react';
import { Text, View } from 'react-native';

import { Button, Card, Chip, Field, Notice, Stat, Toggle } from '@/components/meg';

import { Feedback, Identity, PagedList, Search, fecha, keyProspecto, money, servicio, styles, useMutation, usePage, type Page, type Prospecto, type ProspectosPage } from './common';

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

type Payment = { importe_total: string; importe_anticipo: string; fecha_anticipo: string; fecha_liquidacion: string; proyecto_liquidado: boolean };
type SalesPage = Page & { clientes: Prospecto[] };
const mexicoDay = () => {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Mexico_City', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const part = (kind: string) => parts.find(p => p.type === kind)?.value || '';
  return `${part('year')}-${part('month')}-${part('day')}`;
};
function dateDay(value?: string | null) {
  if (!value) return '';
  if (value.length === 10) return value;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Mexico_City', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(date);
  const part = (kind: string) => parts.find(p => p.type === kind)?.value || '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}
function initialPayment(p: Prospecto): Payment {
  return { importe_total: p.importe_total ?? '', importe_anticipo: p.importe_anticipo ?? '', fecha_anticipo: p.fecha_anticipo ?? '', fecha_liquidacion: dateDay(p.fecha_liquidacion), proyecto_liquidado: Boolean(p.proyecto_liquidado) };
}
function cents(value: string) {
  if (!/^\d+(?:\.\d{1,2})?$/.test(value) || value.length > 24) return null;
  const [whole, decimal = ''] = value.split('.');
  const n = BigInt(whole) * 100n + BigInt(decimal.padEnd(2, '0'));
  return n <= 999999999999n ? n : null;
}
function validDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(new Date(`${value}T12:00:00Z`).getTime()) && new Date(`${value}T12:00:00Z`).toISOString().slice(0, 10) === value;
}

function PaymentCard({ person, busy, onSave }: { person: Prospecto; busy: boolean; onSave: (p: Prospecto, payment: Payment) => Promise<boolean> }) {
  const [draft, setDraft] = useState<Payment | null>(null);
  const [confirming, setConfirming] = useState(false);
  const payment = draft || initialPayment(person);
  function cambiar<K extends keyof Payment>(field: K, value: Payment[K]) {
    const next = { ...payment, [field]: value };
    if (field === 'proyecto_liquidado' && value && !next.fecha_liquidacion) next.fecha_liquidacion = mexicoDay();
    setConfirming(false); setDraft(next);
  }
  async function guardar() { if (await onSave(person, payment)) { setDraft(null); setConfirming(false); } }
  return <Card><Identity person={person} /><View style={styles.row}><Chip label={person.origen || person.fuente} /><Chip label={person.proyecto_liquidado ? 'Liquidado' : 'Pendiente de pago'} selected={Boolean(person.proyecto_liquidado)} /></View>
    <Text style={styles.muted}>{servicio(person.servicio_recomendado)} · Saldo: {person.proyecto_liquidado ? money(0) : person.importe_total == null ? 'Sin capturar' : money(Number(person.importe_total) - Number(person.importe_anticipo))}</Text>
    <Field label="Importe total (MXN) *" placeholder="6000.00" value={payment.importe_total} onChangeText={v => cambiar('importe_total', v)} keyboardType="decimal-pad" maxLength={14} />
    <Field label="Anticipo (MXN) *" placeholder="3000.00" value={payment.importe_anticipo} onChangeText={v => cambiar('importe_anticipo', v)} keyboardType="decimal-pad" maxLength={14} />
    <Field label="Fecha del anticipo (AAAA-MM-DD) *" placeholder="2026-10-24" value={payment.fecha_anticipo} onChangeText={v => cambiar('fecha_anticipo', v)} maxLength={10} autoCapitalize="none" />
    <Toggle label="Proyecto completamente liquidado" value={payment.proyecto_liquidado} onValueChange={v => cambiar('proyecto_liquidado', v)} disabled={busy} />
    {payment.proyecto_liquidado ? <Field label="Fecha de liquidación (AAAA-MM-DD) *" value={payment.fecha_liquidacion} onChangeText={v => cambiar('fecha_liquidacion', v)} maxLength={10} autoCapitalize="none" /> : null}
    {confirming ? <><Notice message="Confirma que el cliente pagó la totalidad del proyecto. Se registrará en los reportes financieros." tone="info" />
      <Button label="Confirmar pago y guardar" onPress={() => void guardar()} disabled={busy} />
      <Button label="Seguir editando" onPress={() => setConfirming(false)} variant="secondary" disabled={busy} /></> : <Button label="Guardar importes y estado" disabled={!draft || busy} onPress={() => payment.proyecto_liquidado && !person.proyecto_liquidado ? setConfirming(true) : void guardar()} />}
  </Card>;
}

export function GestionVentasScreen() {
  const page = usePage<SalesPage>('gestion-ventas/');
  const mutation = useMutation();
  async function guardar(p: Prospecto, payment: Payment) {
    const total = cents(payment.importe_total); const anticipo = cents(payment.importe_anticipo);
    if (total === null || anticipo === null || total <= 0n || anticipo > total) {
      mutation.setError('Captura un total mayor que cero y un anticipo entre cero y el total, con hasta dos decimales y sin separadores de miles.'); return false;
    }
    const hoy = mexicoDay();
    if (!validDate(payment.fecha_anticipo) || payment.fecha_anticipo > hoy) { mutation.setError('La fecha del anticipo debe ser válida y no estar en el futuro.'); return false; }
    if (payment.proyecto_liquidado && (!validDate(payment.fecha_liquidacion) || payment.fecha_liquidacion < payment.fecha_anticipo || payment.fecha_liquidacion > hoy)) {
      mutation.setError('La liquidación debe ser igual o posterior al anticipo y no estar en el futuro.'); return false;
    }
    return mutation.mutate(keyProspecto(p), `gestion-ventas/${p.id}/liquidacion/`, { fuente: p.fuente, ...payment, fecha_liquidacion: payment.proyecto_liquidado ? payment.fecha_liquidacion : null }, page.recargar);
  }
  return <PagedList title="Cobros de ventas" subtitle="Importes, anticipos y liquidaciones en pesos mexicanos." items={page.datos?.clientes || []} keyExtractor={keyProspecto}
    renderItem={p => <PaymentCard person={p} busy={Boolean(mutation.busy) || page.cargando} onSave={guardar} />}
    header={<><Search value={page.search} onChange={page.setSearch} onSearch={page.buscar} /><Feedback error={mutation.error} success={mutation.success} />
      {page.datos ? <View style={styles.row}><Stat label="Ventas" value={String(page.datos.totales?.ventas ?? 0)} /><Stat label="Liquidadas" value={String(page.datos.totales?.liquidados ?? 0)} /><Stat label="Pendientes" value={String(page.datos.totales?.pendientes ?? 0)} /></View> : null}</>}
    loading={page.cargando} error={page.error} recargar={page.recargar} pagina={page.pagina} paginas={page.datos?.paginas || 0} setPagina={page.setPagina} isAdmin={page.isAdmin} scrollToTopKey={mutation.error || mutation.success} />;
}
