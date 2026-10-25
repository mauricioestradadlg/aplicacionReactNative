import { useState } from 'react';
import { Text, View } from 'react-native';

import { Button, Card, Chip, Notice } from '@/components/meg';

import { Feedback, Identity, PagedList, fecha, servicio, styles, useMutation, usePage, type Page } from './common';

type Review = {
  id: string; nombre: string; negocio: string; correo: string; servicio: string; calificacion: number; titulo: string;
  comentario: string; estado: string; autoriza_publicacion: boolean; correo_verificado: boolean;
  cliente_coincide: boolean; verificada: boolean; fecha_creacion: string; fecha_publicacion?: string;
};
type ReviewsPage = Page & { resenas: Review[] };
type Decision = 'aprobar' | 'rechazar';

export function ResenasScreen() {
  const page = usePage<ReviewsPage>('resenas/');
  const mutation = useMutation();
  const [estado, setEstado] = useState('pendiente');
  const [confirm, setConfirm] = useState<{ id: string; decision: Decision } | null>(null);
  function filtrar(value: string) { setEstado(value); page.setPagina(1); page.setExtra(`&estado=${value}`); setConfirm(null); }
  async function decidir(r: Review, decision: Decision) {
    await mutation.mutate(r.id, `resenas/${r.id}/decision/`, { decision }, async () => { setConfirm(null); await page.recargar(); });
  }
  return <PagedList title="Reseñas de clientes" subtitle="Revisa testimonios antes de publicarlos." items={page.datos?.resenas || []} keyExtractor={r => r.id}
    header={<><View style={styles.row}>{[['pendiente', 'Pendientes'], ['aprobada', 'Aprobadas'], ['rechazada', 'Rechazadas']].map(([value, label]) => <Chip key={value}
      label={`${label}${page.datos?.totales ? ` (${page.datos.totales[value] || 0})` : ''}`} selected={estado === value} onPress={() => filtrar(value)} />)}</View>
      <Feedback error={mutation.error} success={mutation.success} /></>}
    renderItem={r => <Card><Identity person={r} /><View style={styles.row}><Chip label={`${r.calificacion}/5 estrellas`} /><Chip label={servicio(r.servicio)} /></View>
      {r.titulo ? <Text style={styles.heading}>{r.titulo}</Text> : null}<Text style={styles.body}>{r.comentario}</Text>
      <Text style={styles.muted}>Recibida: {fecha(r.fecha_creacion)}</Text>
      <View style={styles.row}><Chip label={r.correo_verificado ? 'Correo verificado' : 'Correo sin verificar'} selected={r.correo_verificado} />
        <Chip label={r.cliente_coincide ? 'Cliente registrado' : 'Cliente sin coincidencia'} selected={r.cliente_coincide} />
        <Chip label={r.autoriza_publicacion ? 'Publicación autorizada' : 'Sin autorización'} selected={r.autoriza_publicacion} /></View>
      {r.estado === 'pendiente' ? confirm?.id === r.id ? <><Notice message={confirm.decision === 'aprobar' ? `Al aprobar, la reseña de ${r.nombre} quedará visible en tu página web.` : `Se rechazará la reseña de ${r.nombre}.`} tone="info" />
        <Button label={confirm.decision === 'aprobar' ? 'Confirmar aprobación' : 'Confirmar rechazo'} onPress={() => void decidir(r, confirm.decision)} variant={confirm.decision === 'aprobar' ? 'primary' : 'danger'} disabled={Boolean(mutation.busy)} loading={mutation.busy === r.id} />
        <Button label="Cancelar" onPress={() => setConfirm(null)} variant="secondary" disabled={Boolean(mutation.busy)} /></> : <>
          <Button label="Aprobar y publicar" onPress={() => setConfirm({ id: r.id, decision: 'aprobar' })} disabled={Boolean(mutation.busy) || !r.autoriza_publicacion || !r.correo_verificado || !r.cliente_coincide} />
          <Button label="Rechazar reseña" onPress={() => setConfirm({ id: r.id, decision: 'rechazar' })} variant="danger" disabled={Boolean(mutation.busy)} /></> : <Text style={styles.muted}>{r.estado === 'aprobada' ? `Publicada: ${fecha(r.fecha_publicacion)}` : 'Reseña rechazada'}</Text>}
    </Card>}
    loading={page.cargando} error={page.error} recargar={page.recargar} pagina={page.pagina} paginas={page.datos?.paginas || 0} setPagina={page.setPagina} isAdmin={page.isAdmin} scrollToTopKey={mutation.error || mutation.success} />;
}
