import { useState } from 'react';
import { Text, View } from 'react-native';

import { Button, Card, Chip, Field, Notice, SectionTitle, Toggle } from '@/components/meg';

import { Feedback, Identity, PagedList, Search, fecha, keyProspecto, servicio, styles, useMutation, usePage, type Prospecto, type ProspectosPage } from './common';

const blank = { telefono: '', nombre: '', negocio: '', servicio_recomendado: '', respondio_mensajes: false };
type Form = typeof blank;
type PotentialForm = Form & { origen: string };
const services = [['', 'Sin definir'], ['landing-page', 'Landing Page'], ['sitio-web', 'Sitio Web']];
const validPhone = (value: string) => /^\+?[0-9 ()-]{10,25}$/.test(value.trim()) && /^\d{10,15}$/.test(value.replace(/\D/g, ''));

function ServiceChoice({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <View style={{ gap: 8 }}><Text style={styles.muted}>Servicio recomendado</Text><View style={styles.row}>{services.map(([id, label]) => <Chip key={id} label={label} selected={value === id} onPress={() => onChange(id)} />)}</View></View>;
}

export function ProspectosScreen() {
  const page = usePage<ProspectosPage>('oferta-valor/prospectos/');
  const mutation = useMutation();
  const [form, setForm] = useState<Form>(blank);
  const [editing, setEditing] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  function cambiar<K extends keyof Form>(campo: K, value: Form[K]) { setForm(prev => ({ ...prev, [campo]: value })); }
  function editar(p: Prospecto) {
    setForm({ telefono: p.telefono, nombre: p.nombre || '', negocio: p.negocio || '', servicio_recomendado: p.servicio_recomendado || '', respondio_mensajes: Boolean(p.respondio_mensajes) });
    setEditing(p.id); setShowForm(true); mutation.setError('');
  }
  function cancelar() { setForm(blank); setEditing(null); setShowForm(false); }
  async function guardar() {
    if (!validPhone(form.telefono)) { mutation.setError('Ingresa un teléfono válido de 10 a 15 dígitos.'); return; }
    await mutation.mutate('form', editing ? `oferta-valor/prospectos/${editing}/editar/` : 'oferta-valor/prospectos/', form, async () => { cancelar(); await page.recargar(); });
  }
  return <PagedList title="Prospectos" subtitle="Oferta de valor · contactos de WhatsApp." items={page.datos?.prospectos || []} keyExtractor={keyProspecto}
    renderItem={p => <Card><Identity person={p} /><View style={styles.row}>
      <Chip label={p.brindo_nombre ? 'Brindó nombre' : 'Sin nombre'} selected={p.brindo_nombre} />
      <Chip label={p.respondio_mensajes ? 'Respondió mensajes' : 'Sin respuesta'} selected={p.respondio_mensajes} /></View>
      <Text style={styles.muted}>{servicio(p.servicio_recomendado)} · {fecha(p.fecha_registro)}</Text>
      <Button label="Editar prospecto" onPress={() => editar(p)} variant="secondary" disabled={Boolean(mutation.busy)} /></Card>}
    header={<><Search value={page.search} onChange={page.setSearch} onSearch={page.buscar} />
      {!showForm ? <Button label="Registrar prospecto" onPress={() => { setForm(blank); setEditing(null); setShowForm(true); }} /> : <Card>
        <SectionTitle>{editing ? 'Editar prospecto' : 'Nuevo prospecto'}</SectionTitle>
        <Field label="Teléfono / WhatsApp *" value={form.telefono} onChangeText={v => cambiar('telefono', v)} keyboardType="phone-pad" maxLength={25} />
        <Field label="Nombre, si lo proporcionó" value={form.nombre} onChangeText={v => cambiar('nombre', v)} maxLength={100} />
        <Field label="Negocio" value={form.negocio} onChangeText={v => cambiar('negocio', v)} maxLength={120} />
        <ServiceChoice value={form.servicio_recomendado} onChange={v => cambiar('servicio_recomendado', v)} />
        <Toggle label="Respondió mensajes" value={form.respondio_mensajes} onValueChange={v => cambiar('respondio_mensajes', v)} />
        <Text style={styles.muted}>Al guardar un nombre y confirmar una respuesta, el contacto aparece en Clientes potenciales.</Text>
        <Button label="Guardar prospecto" onPress={() => void guardar()} loading={mutation.busy === 'form'} disabled={Boolean(mutation.busy)} />
        <Button label="Cancelar" onPress={cancelar} variant="secondary" disabled={Boolean(mutation.busy)} /></Card>}
      <Feedback error={mutation.error} success={mutation.success} />
      {page.datos ? <Text style={styles.muted}>{page.datos.total} prospectos</Text> : null}</>}
    loading={page.cargando} error={page.error} recargar={page.recargar} pagina={page.pagina} paginas={page.datos?.paginas || 0} setPagina={page.setPagina} isAdmin={page.isAdmin} scrollToTopKey={mutation.error || mutation.success || (showForm ? editing || 'new' : '')} />;
}

function PotentialCard({ person, busy, onSave, onAppointment }: {
  person: Prospecto; busy: boolean; onSave: (p: Prospecto, form: PotentialForm) => Promise<boolean>; onAppointment: (p: Prospecto) => void;
}) {
  const [editing, setEditing] = useState(false);
  const initial = (): PotentialForm => ({ telefono: person.telefono, nombre: person.nombre, negocio: person.negocio || '', servicio_recomendado: person.servicio_recomendado || '', origen: person.origen || 'WhatsApp', respondio_mensajes: Boolean(person.respondio_mensajes) });
  const [form, setForm] = useState<PotentialForm>(initial);
  function cambiar<K extends keyof PotentialForm>(campo: K, value: PotentialForm[K]) { setForm(prev => ({ ...prev, [campo]: value })); }
  async function guardar() { if (await onSave(person, form)) setEditing(false); }
  return <Card><Identity person={person} /><View style={styles.row}><Chip label={person.origen || person.fuente} /><Chip label={person.cita_agendada_en ? 'Cita agendada' : 'Sin cita'} selected={Boolean(person.cita_agendada_en)} /></View>
    {editing ? <><Field label="Nombre *" value={form.nombre} onChangeText={v => cambiar('nombre', v)} maxLength={100} />
      <Field label="Teléfono *" value={form.telefono} onChangeText={v => cambiar('telefono', v)} maxLength={25} keyboardType="phone-pad" />
      <Field label="Negocio" value={form.negocio} onChangeText={v => cambiar('negocio', v)} maxLength={120} />
      <ServiceChoice value={form.servicio_recomendado} onChange={v => cambiar('servicio_recomendado', v)} />
      <Text style={styles.muted}>Origen comercial</Text><View style={styles.row}>{['WhatsApp', 'Email Marketing'].map(o => <Chip key={o} label={o} selected={form.origen === o} onPress={() => cambiar('origen', o)} />)}</View>
      <Button label="Guardar datos" onPress={() => void guardar()} disabled={busy} />
      <Button label="Cancelar edición" onPress={() => setEditing(false)} variant="secondary" disabled={busy} /></> : <>
      <Text style={styles.muted}>{servicio(person.servicio_recomendado)} · Cita: {person.cita_agendada_en ? fecha(person.cita_agendada_en) : 'Sin agendar'}</Text>
      <Button label="Editar datos" onPress={() => { setForm(initial()); setEditing(true); }} variant="secondary" disabled={busy} />
      <Button label={person.cita_agendada_en ? 'Quitar marca de cita' : 'Confirmar cita agendada'} onPress={() => onAppointment(person)} variant="secondary" disabled={busy} /></>}
  </Card>;
}

export function PotencialesScreen() {
  const page = usePage<ProspectosPage>('oferta-valor/potenciales/');
  const mutation = useMutation();
  async function guardar(p: Prospecto, form: PotentialForm) {
    if (!form.nombre.trim()) { mutation.setError('El nombre del cliente potencial es obligatorio.'); return false; }
    if (!validPhone(form.telefono)) { mutation.setError('Ingresa un teléfono válido de 10 a 15 dígitos.'); return false; }
    return mutation.mutate(keyProspecto(p), `oferta-valor/potenciales/${p.id}/editar/`, { fuente: p.fuente, nombre: form.nombre, telefono: form.telefono, negocio: form.negocio, servicio_recomendado: form.servicio_recomendado, origen: form.origen }, page.recargar);
  }
  function cita(p: Prospecto) { void mutation.mutate(keyProspecto(p), `oferta-valor/potenciales/${p.id}/cita/`, { fuente: p.fuente, cita_agendada: !p.cita_agendada_en }, page.recargar); }
  return <PagedList title="Clientes potenciales" subtitle="Contactos calificados de WhatsApp y Email Marketing." items={page.datos?.prospectos || []} keyExtractor={keyProspecto}
    renderItem={p => <PotentialCard person={p} busy={Boolean(mutation.busy) || page.cargando} onSave={guardar} onAppointment={cita} />}
    header={<><Search value={page.search} onChange={page.setSearch} onSearch={page.buscar} /><Notice message="La marca de cita confirma una cita que ya agendaste con el cliente." tone="info" />
      <Feedback error={mutation.error} success={mutation.success} />{page.datos ? <Text style={styles.muted}>{page.datos.total} clientes potenciales</Text> : null}</>}
    loading={page.cargando} error={page.error} recargar={page.recargar} pagina={page.pagina} paginas={page.datos?.paginas || 0} setPagina={page.setPagina} isAdmin={page.isAdmin} scrollToTopKey={mutation.error || mutation.success} />;
}
