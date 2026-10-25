import { useState } from 'react';
import { Text, View } from 'react-native';

import { Card, Chip, Notice, Toggle } from '@/components/meg';

import { Feedback, Identity, PagedList, Search, fecha, styles, useMutation, usePage, type Lead, type LeadsPage } from './common';

export function LeadsScreen() {
  const page = usePage<LeadsPage>('lead-magnet/registros/');
  const [plantilla, setPlantilla] = useState('');
  function filtrar(value: string) { setPlantilla(value); page.setPagina(1); page.setExtra(value ? `&plantilla=${value}` : ''); }
  return <PagedList title="Registros de leads" subtitle="Solicitudes de las plantillas gratuitas." items={page.datos?.leads || []}
    keyExtractor={p => p.id} renderItem={p => <Card><Identity person={p} />
      <View style={styles.row}><Chip label={p.plantilla === 'restaurante' ? 'Restaurante' : 'Negocio regular'} /><Chip label={p.acepto_correos ? 'Aceptó correos' : 'Sin consentimiento para correos'} /></View>
      <Text style={styles.muted}>Registro: {fecha(p.fecha_registro)}</Text></Card>}
    header={<><Search value={page.search} onChange={page.setSearch} onSearch={page.buscar} />
      <View style={styles.row}>{[['', 'Todas'], ['restaurante', 'Restaurantes'], ['negocio', 'Negocios']].map(([value, label]) => <Chip key={value} label={label} selected={plantilla === value} onPress={() => filtrar(value)} />)}</View>
      {page.datos ? <Text style={styles.muted}>{page.datos.total} registros encontrados</Text> : null}</>}
    loading={page.cargando} error={page.error} recargar={page.recargar} pagina={page.pagina} paginas={page.datos?.paginas || 0} setPagina={page.setPagina} isAdmin={page.isAdmin} />;
}

const seguimientos = [
  { campo: 'tips_enviados', key: 'tips_enviados_en', label: 'Consejos enviados' },
  { campo: 'feedback_enviado', key: 'feedback_enviado_en', label: 'Feedback enviado' },
  { campo: 'oportunidad_comercial', key: 'oportunidad_comercial_en', label: 'Oportunidad comercial' },
] as const;

export function EmailMarketingScreen() {
  const page = usePage<LeadsPage>('lead-magnet/email-marketing/');
  const mutation = useMutation();
  async function cambiar(lead: Lead, campo: string, valor: boolean) {
    await mutation.mutate(`${lead.id}:${campo}`, `lead-magnet/email-marketing/${lead.id}/estado/`, { campo, valor }, page.recargar);
  }
  return <PagedList title="Email Marketing" subtitle="Seguimiento de leads con consentimiento." items={page.datos?.leads || []} keyExtractor={p => p.id}
    renderItem={p => <Card><Identity person={p} />{seguimientos.map(op => <View key={op.campo}>
      <Toggle label={op.label} value={Boolean(p[op.key])} disabled={Boolean(mutation.busy) || page.cargando} onValueChange={value => void cambiar(p, op.campo, value)} />
      <Text style={styles.muted}>{fecha(p[op.key])}</Text></View>)}</Card>}
    header={<><Search value={page.search} onChange={page.setSearch} onSearch={page.buscar} />
      <Notice message="Estos controles registran acciones ya realizadas. El envío de correos se hace por los canales habituales." tone="info" />
      <Feedback error={mutation.error} success={mutation.success} />
      {page.datos ? <Text style={styles.muted}>{page.datos.total} leads con consentimiento</Text> : null}</>}
    loading={page.cargando} error={page.error} recargar={page.recargar} pagina={page.pagina} paginas={page.datos?.paginas || 0} setPagina={page.setPagina} isAdmin={page.isAdmin} scrollToTopKey={mutation.error || mutation.success} />;
}
