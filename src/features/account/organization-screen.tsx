import { router, type Href } from 'expo-router';
import { useRef, useState } from 'react';
import { ActivityIndicator, Text } from 'react-native';
import { Button, Card, Chip, Empty, Field, Notice, Row, Screen, SectionTitle, colors, sharedStyles } from '@/components/meg';
import { useSession, type Organizacion, type Rol } from '@/context/session';
import { useConsulta } from '@/hooks/use-consulta';
import { peticionSistema } from '@/services/api';
import { Roles, errorTexto, nombreRol, roles } from './common';

type Invitacion = { usuario: string; rol: Rol };

export function OrganizacionesScreen() {
  const { usuario, comprobarSesion } = useSession();
  const [modo, setModo] = useState<'elegir' | 'crear' | 'unirse'>('elegir');
  const [nombre, setNombre] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [invitaciones, setInvitaciones] = useState<Invitacion[]>([]);
  const [invitado, setInvitado] = useState('');
  const [rol, setRol] = useState<Rol>('desarrollador');
  const [busqueda, setBusqueda] = useState('');
  const [buscar, setBuscar] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const bloqueo = useRef(false);
  const habilitado = Boolean(usuario && usuario.estado_acceso !== 'aceptado' && usuario.estado_acceso !== 'pendiente');
  const { datos, cargando, error: errorConsulta, recargar } = useConsulta<{ organizaciones: Organizacion[] }>(habilitado && modo === 'unirse' && buscar.length >= 2 ? `organizaciones/?buscar=${encodeURIComponent(buscar)}` : null);
  function agregar() {
    const valor = invitado.trim().toLowerCase();
    if (!valor) { setError('Escribe el nombre de usuario de la persona que quieres invitar.'); return; }
    if (valor === usuario?.usuario || invitaciones.some(item => item.usuario === valor)) { setError('Ese usuario ya forma parte de esta lista.'); return; }
    if (invitaciones.length >= 20) { setError('Puedes invitar hasta 20 colaboradores al crear la organización.'); return; }
    setInvitaciones(prev => [...prev, { usuario: valor, rol }]); setInvitado(''); setError('');
  }
  async function guardar(organizacionId?: string) {
    if (bloqueo.current) return;
    setError('');
    if (!organizacionId && !nombre.trim()) { setError('Escribe el nombre de tu organización.'); return; }
    if (!organizacionId && invitado.trim()) { setError('Añade el usuario a la lista de invitaciones o limpia ese campo antes de continuar.'); return; }
    bloqueo.current = true; setLoading(true);
    try {
      await peticionSistema(organizacionId ? 'organizaciones/solicitar/' : 'organizaciones/', { metodo: 'POST', datos: organizacionId ? { organizacion_id: organizacionId } : { nombre: nombre.trim(), descripcion: descripcion.trim(), invitaciones } });
      await comprobarSesion();
      router.replace('/' as Href);
    } catch (err) { setError(errorTexto(err)); }
    finally { bloqueo.current = false; setLoading(false); }
  }
  function consultar() {
    if (busqueda.trim().length < 2) { setError('Escribe al menos dos caracteres para buscar.'); return; }
    setError('');
    const siguiente = busqueda.trim();
    if (siguiente === buscar) void recargar(); else setBuscar(siguiente);
  }
  return <Screen title="Encuentra tu equipo" subtitle="Crea el espacio de tu empresa o únete a una organización existente.">
    {!habilitado ? <Card><SectionTitle>{usuario?.estado_acceso === 'pendiente' ? 'Tu solicitud está en revisión' : 'Ya tienes una organización'}</SectionTitle><Text style={sharedStyles.body}>{usuario?.organizacion?.nombre}</Text><Text style={sharedStyles.caption}>{usuario?.estado_acceso === 'pendiente' ? 'Un administrador debe aceptar tu solicitud y asignarte un rol.' : 'Vuelve al inicio para acceder a tus módulos.'}</Text><Button label="Volver al inicio" onPress={() => router.replace('/' as Href)} /></Card> : <>
      {modo === 'elegir' ? <>
        <Card><Chip label="Para responsables de equipo" /><SectionTitle>Crear organización</SectionTitle><Text style={sharedStyles.body}>Administra clientes, proyectos y finanzas de tu empresa. Tú tendrás el rol de administrador.</Text><Button label="Crear mi organización" icon="add-outline" onPress={() => { setModo('crear'); setError(''); }} /></Card>
        <Card><Chip label="Para colaboradores" /><SectionTitle>Unirme a una organización</SectionTitle><Text style={sharedStyles.body}>Busca a tu empresa y solicita acceso. Su administrador te asignará el módulo correspondiente.</Text><Button label="Buscar organización" icon="search-outline" variant="secondary" onPress={() => { setModo('unirse'); setError(''); }} /></Card>
      </> : <Button label="Cambiar de opción" variant="secondary" disabled={loading} onPress={() => { setModo('elegir'); setError(''); }} />}
      {modo === 'crear' && <>
        <Card><SectionTitle>Tu organización</SectionTitle><Field label="Nombre de la organización" placeholder="Ej. Estudio de software Norte" value={nombre} onChangeText={setNombre} maxLength={120} editable={!loading} /><Field label="Descripción" placeholder="¿Qué hace tu empresa?" value={descripcion} onChangeText={setDescripcion} multiline maxLength={2000} editable={!loading} /></Card>
        <Card><SectionTitle>Invitar colaboradores</SectionTitle><Text style={sharedStyles.caption}>Opcional. Deben tener una cuenta registrada y estar disponibles para unirse. Entrarán con el rol que elijas.</Text><Field label="Nombre de usuario" placeholder="Usuario registrado en la aplicación" value={invitado} onChangeText={setInvitado} autoCapitalize="none" autoCorrect={false} maxLength={80} editable={!loading} /><Roles value={rol} onChange={setRol} disabled={loading} /><Text style={sharedStyles.caption}>{roles.find(item => item.valor === rol)?.descripcion}</Text><Button label="Añadir a invitaciones" variant="secondary" disabled={loading || !invitado.trim()} onPress={agregar} />
          {invitaciones.map(item => <Card key={item.usuario}><Text style={sharedStyles.body}>@{item.usuario}</Text><Chip label={nombreRol(item.rol)} /><Button label={`Quitar a ${item.usuario}`} variant="secondary" disabled={loading} onPress={() => setInvitaciones(prev => prev.filter(actual => actual.usuario !== item.usuario))} /></Card>)}
        </Card>
        <Notice message={error} /><Button label="Crear y continuar" loading={loading} onPress={() => void guardar()} />
      </>}
      {modo === 'unirse' && <>
        <Card><Field label="Nombre de la organización" placeholder="Busca por nombre" value={busqueda} onChangeText={setBusqueda} maxLength={120} editable={!loading} onSubmitEditing={consultar} returnKeyType="search" /><Button label="Buscar" icon="search-outline" onPress={consultar} disabled={loading || cargando} /></Card>
        <Notice message={error || errorConsulta} />
        {cargando && <ActivityIndicator color={colors.primary} />}
        {datos && <><Row><SectionTitle>Organizaciones encontradas</SectionTitle><Chip label={String(datos.organizaciones.length)} /></Row>{datos.organizaciones.length ? datos.organizaciones.map(item => <Card key={item.id}><SectionTitle>{item.nombre}</SectionTitle>{Boolean(item.descripcion) && <Text style={sharedStyles.body}>{item.descripcion}</Text>}<Button label="Solicitar acceso" loading={loading} onPress={() => void guardar(item.id)} /></Card>) : <Empty message="No encontramos organizaciones con ese nombre. Prueba con otra búsqueda." />}</>}
      </>}
      {modo === 'elegir' && <Notice message={error} />}
    </>}
  </Screen>;
}
