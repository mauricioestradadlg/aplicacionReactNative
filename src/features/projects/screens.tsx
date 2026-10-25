import { useRef, useState } from 'react';
import { router, type Href } from 'expo-router';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Button, Card, Chip, Empty, Field, Notice, Pagination, Row, Screen, SectionTitle, colors, sharedStyles } from '@/components/meg';
import { useSession } from '@/context/session';
import { useConsulta } from '@/hooks/use-consulta';
import { peticionSistema } from '@/services/api';

type Estado = 'por_hacer' | 'en_progreso' | 'completado';
type Proyecto = {
  id: string; fuente: string; nombre: string | null; negocio: string | null;
  telefono: string | null; origen: string; servicio_recomendado: string | null;
  total_requerimientos: number; completados: number;
};
type Requerimiento = { id: string; titulo: string; descripcion: string; estado: Estado };
type ProyectosRespuesta = { proyectos: Proyecto[]; total: number; pagina: number; paginas: number };
type DetalleRespuesta = { proyecto: Proyecto; requerimientos_definidos: boolean; requerimientos: Requerimiento[] };
type Borrador = { clave: number; titulo: string; descripcion: string };

const estados: { estado: Estado; titulo: string; color: string }[] = [
  { estado: 'por_hacer', titulo: 'Por hacer', color: '#8A99AD' },
  { estado: 'en_progreso', titulo: 'En progreso', color: '#176CF2' },
  { estado: 'completado', titulo: 'Completado', color: '#15946E' },
];
const servicio = (valor: string | null) => valor === 'landing-page' ? 'Landing Page' : valor === 'sitio-web' ? 'Sitio Web' : valor || 'Servicio por definir';
const mensajeError = (error: unknown) => error instanceof Error ? error.message : 'No fue posible guardar los cambios. Intenta nuevamente.';
const detalleRuta = (fuente: string, id: string, tablero = false): Href => ({ pathname: '/proyectos/[fuente]/[id]', params: { fuente, id, vista: tablero ? 'tablero' : 'requerimientos' } }) as Href;
function bytesUtf8(texto: string) {
  let total = 0;
  for (const simbolo of texto) {
    const punto = simbolo.codePointAt(0) || 0;
    total += punto <= 0x7F ? 1 : punto <= 0x7FF ? 2 : punto <= 0xFFFF ? 3 : 4;
  }
  return total;
}

function Progreso({ completados, total }: { completados: number; total: number }) {
  return <View style={styles.progressContainer}>
    <Text style={sharedStyles.caption}>{completados} de {total} requerimientos completados</Text>
    <View accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: Math.max(total, 1), now: completados }} style={styles.progressTrack}>
      <View style={[styles.progressFill, { width: `${Math.min(100, total > 0 ? completados / total * 100 : 0)}%` }]} />
    </View>
  </View>;
}

export function ProyectosScreen({ gestion = false }: { gestion?: boolean }) {
  const { usuario } = useSession();
  const admin = usuario?.rol === 'admin';
  const [busqueda, setBusqueda] = useState('');
  const [buscar, setBuscar] = useState('');
  const [pagina, setPagina] = useState(1);
  const params = new URLSearchParams({ pagina: String(pagina), buscar });
  const { datos, cargando, error, recargar } = useConsulta<ProyectosRespuesta>(admin ? `proyectos/${gestion ? 'gestion' : 'pendientes'}/?${params}` : null);
  const filtrar = () => { setPagina(1); setBuscar(busqueda.trim()); };
  return <Screen title={gestion ? 'Gestión de proyectos' : 'Requerimientos'} subtitle={gestion ? 'Organiza el trabajo y sigue el avance de cada proyecto.' : 'Define el alcance de tus ventas cerradas para comenzar su desarrollo.'} refreshing={cargando} onRefresh={recargar}>
    {!admin ? <Notice message="Solo administradores pueden consultar y modificar los proyectos." /> : <>
      <Card>
        <Field label="Buscar proyecto o cliente" placeholder="Nombre, negocio o teléfono" value={busqueda} onChangeText={setBusqueda} maxLength={100} returnKeyType="search" onSubmitEditing={filtrar} />
        <Button label="Buscar" onPress={filtrar} disabled={cargando} variant="secondary" />
      </Card>
      {error ? <><Notice message={error} /><Button label="Reintentar" onPress={recargar} variant="secondary" /></> : null}
      {cargando && !datos ? <ActivityIndicator color={colors.primary} /> : null}
      {datos ? <>
        <SectionTitle>{datos.total} {datos.total === 1 ? 'proyecto' : 'proyectos'} {gestion ? 'en gestión' : 'pendientes'}</SectionTitle>
        {datos.proyectos.length === 0 ? <Empty message={buscar ? 'No se encontraron proyectos para esta búsqueda.' : gestion ? 'Todavía no hay proyectos con requerimientos definidos.' : 'No hay ventas cerradas pendientes de requerimientos.'} /> : datos.proyectos.map((proyecto) => <Card key={`${proyecto.fuente}-${proyecto.id}`}>
          <Row><Chip label={servicio(proyecto.servicio_recomendado)} /><Chip label={proyecto.origen || (proyecto.fuente === 'whatsapp' ? 'WhatsApp' : 'Email Marketing')} /></Row>
          <Text style={styles.projectTitle}>{proyecto.negocio || proyecto.nombre || 'Proyecto sin nombre'}</Text>
          <Text style={sharedStyles.body}>{proyecto.nombre || 'Cliente sin nombre'}</Text>
          <Text style={sharedStyles.caption}>{proyecto.telefono || 'Sin teléfono registrado'}</Text>
          {gestion ? <Progreso completados={proyecto.completados} total={proyecto.total_requerimientos} /> : null}
          <Button label={gestion ? 'Abrir tablero' : 'Definir requerimientos'} onPress={() => router.push(detalleRuta(proyecto.fuente, proyecto.id, gestion))} />
        </Card>)}
        <Pagination pagina={pagina} paginas={datos.paginas} onChange={setPagina} />
        <Button label={gestion ? 'Ver proyectos pendientes' : 'Ver proyectos en gestión'} variant="secondary" onPress={() => router.push((gestion ? '/proyectos/pendientes' : '/proyectos/gestion') as Href)} />
      </> : null}
    </>}
  </Screen>;
}

export function ProyectoDetalleScreen({ fuente, id, tablero = false }: { fuente: string; id: string; tablero?: boolean }) {
  const { usuario } = useSession();
  const admin = usuario?.rol === 'admin';
  const raiz = `proyectos/${encodeURIComponent(fuente)}/${encodeURIComponent(id)}`;
  const { datos, cargando, error, recargar } = useConsulta<DetalleRespuesta>(admin && fuente && id ? `${raiz}/${tablero ? 'kanban' : 'requerimientos'}/` : null);
  const [filas, setFilas] = useState<Borrador[]>([{ clave: 0, titulo: '', descripcion: '' }]);
  const secuencia = useRef(1);
  const bloqueo = useRef(false);
  const [guardando, setGuardando] = useState(false);
  const [errorGuardado, setErrorGuardado] = useState('');
  const [aviso, setAviso] = useState('');
  const [filtroEstado, setFiltroEstado] = useState<Estado>('por_hacer');
  const actualizarFila = (clave: number, campo: 'titulo' | 'descripcion', valor: string) => {
    setFilas((prev) => prev.map((fila) => fila.clave === clave ? { ...fila, [campo]: valor } : fila));
    setErrorGuardado('');
  };
  async function guardar() {
    if (bloqueo.current) return;
    const requerimientos = filas.map(({ titulo, descripcion }) => ({ titulo: titulo.trim(), descripcion: descripcion.trim() }));
    if (requerimientos.some((fila) => !fila.titulo)) { setErrorGuardado('Escribe un título para cada requerimiento o elimina las filas vacías.'); return; }
    if (bytesUtf8(JSON.stringify({ requerimientos })) > 60 * 1024) { setErrorGuardado('Reduce las descripciones: la lista supera el tamaño permitido de 60 KB.'); return; }
    bloqueo.current = true; setGuardando(true); setErrorGuardado(''); setAviso('');
    try {
      await peticionSistema(`${raiz}/requerimientos/`, { metodo: 'POST', datos: { requerimientos } });
      router.replace(detalleRuta(fuente, id, true));
    } catch (err) { setErrorGuardado(mensajeError(err)); }
    finally { bloqueo.current = false; setGuardando(false); }
  }
  async function mover(requerimiento: Requerimiento, estado: Estado) {
    if (bloqueo.current || estado === requerimiento.estado) return;
    bloqueo.current = true; setGuardando(true); setErrorGuardado(''); setAviso('');
    try {
      await peticionSistema(`${raiz}/requerimientos/${encodeURIComponent(requerimiento.id)}/estado/`, { metodo: 'POST', datos: { estado } });
      setAviso(`«${requerimiento.titulo}» se guardó en ${estados.find((item) => item.estado === estado)?.titulo}.`);
      await recargar();
    } catch (err) { setErrorGuardado(mensajeError(err)); }
    finally { bloqueo.current = false; setGuardando(false); }
  }
  const requerimientos = datos?.requerimientos || [];
  return <Screen title={tablero ? 'Tablero del proyecto' : 'Definir requerimientos'} subtitle={tablero ? 'Cada cambio se guarda en el sistema compartido.' : 'Captura los requerimientos para comenzar la gestión.'} refreshing={cargando} onRefresh={guardando ? undefined : recargar}>
    {!admin ? <Notice message="Solo administradores pueden consultar y modificar los proyectos." /> : <>
      {error || errorGuardado ? <Notice message={errorGuardado || error} /> : null}
      {aviso ? <Notice message={aviso} tone="success" /> : null}
      {cargando && !datos ? <ActivityIndicator color={colors.primary} /> : null}
      {error || errorGuardado ? <Button label="Volver a consultar el proyecto" onPress={recargar} disabled={guardando} variant="secondary" /> : null}
      {tablero && !datos && !cargando ? <Button label="Definir requerimientos" onPress={() => router.replace(detalleRuta(fuente, id))} variant="secondary" /> : null}
      {datos ? <>
        <Card>
          <Chip label={servicio(datos.proyecto.servicio_recomendado)} />
          <Text style={styles.projectTitle}>{datos.proyecto.negocio || datos.proyecto.nombre || 'Proyecto'}</Text>
          <Text style={sharedStyles.body}>{datos.proyecto.nombre || 'Cliente sin nombre'}</Text>
          {tablero ? <Progreso completados={requerimientos.filter((item) => item.estado === 'completado').length} total={requerimientos.length} /> : null}
        </Card>
        {tablero ? <>
          <Row>{estados.map((columna) => <Chip key={columna.estado} label={`${columna.titulo} · ${requerimientos.filter((item) => item.estado === columna.estado).length}`} selected={filtroEstado === columna.estado} onPress={() => setFiltroEstado(columna.estado)} />)}</Row>
          {requerimientos.filter((item) => item.estado === filtroEstado).length === 0 ? <Empty message="Sin requerimientos en este estado." /> : requerimientos.filter((item) => item.estado === filtroEstado).map((item) => <Card key={item.id} style={{ borderLeftWidth: 4, borderLeftColor: estados.find((estado) => estado.estado === item.estado)?.color }}>
            <Text style={styles.taskTitle}>{item.titulo}</Text>
            {item.descripcion ? <Text style={sharedStyles.body}>{item.descripcion}</Text> : null}
            <Text style={sharedStyles.caption}>Cambiar estado</Text>
            <Row>{estados.map((estado) => <Button key={estado.estado} label={estado.titulo} variant={item.estado === estado.estado ? 'primary' : 'secondary'} disabled={guardando || item.estado === estado.estado} onPress={() => mover(item, estado.estado)} />)}</Row>
          </Card>)}
        </> : datos.requerimientos_definidos ? <>
          <Notice message="Este proyecto ya tiene requerimientos definidos." tone="info" />
          <Button label="Abrir tablero Kanban" onPress={() => router.replace(detalleRuta(fuente, id, true))} />
        </> : <>
          <Notice message="Puedes añadir hasta 100 requerimientos. Al guardar, todos comenzarán en Por hacer." tone="info" />
          {filas.map((fila, indice) => <Card key={fila.clave}>
            <SectionTitle>Requerimiento {indice + 1}</SectionTitle>
            <Field label="Título *" placeholder="Ej. Inicio de sesión de usuarios" value={fila.titulo} onChangeText={(valor) => actualizarFila(fila.clave, 'titulo', valor)} maxLength={150} editable={!guardando} />
            <Field label="Descripción" placeholder="¿Qué debe permitir el sistema?" value={fila.descripcion} onChangeText={(valor) => actualizarFila(fila.clave, 'descripcion', valor)} maxLength={2000} multiline numberOfLines={3} editable={!guardando} />
            <Button label={`Quitar requerimiento ${indice + 1}`} variant="secondary" disabled={guardando || filas.length === 1} onPress={() => setFilas((prev) => prev.filter((actual) => actual.clave !== fila.clave))} />
          </Card>)}
          <Button label={`Añadir requerimiento (${filas.length}/100)`} variant="secondary" disabled={guardando || filas.length >= 100} onPress={() => { const clave = secuencia.current++; setFilas((prev) => [...prev, { clave, titulo: '', descripcion: '' }]); }} />
          <Button label="Guardar requerimientos" onPress={guardar} loading={guardando} />
        </>}
      </> : null}
    </>}
  </Screen>;
}

const styles = StyleSheet.create({
  projectTitle: { fontSize: 21, fontWeight: '700', color: colors.ink },
  taskTitle: { fontSize: 17, fontWeight: '700', color: colors.ink },
  progressContainer: { gap: 8, paddingVertical: 6 },
  progressTrack: { height: 7, borderRadius: 8, backgroundColor: '#E8EDF5', overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 8, backgroundColor: '#15946E' },
});
