import { useRef, useState } from 'react';
import { ActivityIndicator, Text } from 'react-native';
import { router, type Href } from 'expo-router';
import { Button, Card, Chip, Empty, Field, Notice, Screen, SectionTitle, colors, sharedStyles } from '@/components/meg';
import { useSession, type Rol } from '@/context/session';
import { useConsulta } from '@/hooks/use-consulta';
import { peticionSistema } from '@/services/api';
import { errorTexto, nombreRol } from './common';

export function CuentaScreen() {
  const { usuario, comprobarSesion } = useSession();
  const [form, setForm] = useState({ nombre_completo: usuario?.nombre_completo || '', correo: usuario?.correo || '', telefono: usuario?.telefono || '', usuario: usuario?.usuario || '' });
  const [actual, setActual] = useState('');
  const [contrasena, setContrasena] = useState('');
  const [confirmacion, setConfirmacion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [aviso, setAviso] = useState('');
  const bloqueo = useRef(false);
  const sensible = Boolean(contrasena || form.correo.trim().toLowerCase() !== usuario?.correo || form.usuario.trim().toLowerCase() !== usuario?.usuario || form.telefono.replace(/\D/g, '') !== usuario?.telefono.replace(/\D/g, ''));
  const cambiar = (campo: keyof typeof form, valor: string) => { setForm(prev => ({ ...prev, [campo]: valor })); setAviso(''); };
  async function guardar() {
    if (bloqueo.current) return;
    setError(''); setAviso('');
    if (!form.nombre_completo.trim() || !form.correo.trim() || !form.telefono.trim() || !form.usuario.trim()) { setError('Completa todos los datos de tu cuenta.'); return; }
    if (sensible && !actual) { setError('Escribe tu contraseña actual para confirmar estos cambios.'); return; }
    if (contrasena && contrasena.length < 10) { setError('Tu nueva contraseña debe tener al menos 10 caracteres.'); return; }
    if (contrasena !== confirmacion) { setError('Las contraseñas nuevas no coinciden.'); return; }
    bloqueo.current = true; setLoading(true);
    try {
      await peticionSistema('cuenta/', { metodo: 'PATCH', datos: { ...form, nombre_completo: form.nombre_completo.trim(), usuario: form.usuario.trim().toLowerCase(), correo: form.correo.trim().toLowerCase(), telefono: form.telefono.trim(), contrasena_actual: actual, ...(contrasena ? { contrasena } : {}) } });
      setActual(''); setContrasena(''); setConfirmacion('');
      await comprobarSesion(); setAviso('Los datos de tu cuenta se guardaron.');
    } catch (err) { setError(errorTexto(err)); }
    finally { bloqueo.current = false; setLoading(false); }
  }
  return <Screen title="Configuración de cuenta" subtitle="Mantén tus datos actualizados y administra tu acceso.">
    <Card><Chip label={nombreRol(usuario?.rol || null)} /><Text style={sharedStyles.body}>{usuario?.organizacion?.nombre || 'Sin organización'}</Text><Text style={sharedStyles.caption}>El administrador de tu organización asigna los permisos de cada módulo.</Text></Card>
    <Card>
      <SectionTitle>Datos personales</SectionTitle>
      <Field label="Nombre completo" value={form.nombre_completo} onChangeText={v => cambiar('nombre_completo', v)} autoComplete="name" maxLength={150} editable={!loading} />
      <Field label="Correo electrónico" value={form.correo} onChangeText={v => cambiar('correo', v)} keyboardType="email-address" autoCapitalize="none" autoCorrect={false} autoComplete="email" maxLength={254} editable={!loading} />
      <Field label="Teléfono" value={form.telefono} onChangeText={v => cambiar('telefono', v)} keyboardType="phone-pad" autoComplete="tel" maxLength={25} editable={!loading} />
      <Field label="Nombre de usuario" value={form.usuario} onChangeText={v => cambiar('usuario', v)} autoCapitalize="none" autoCorrect={false} autoComplete="username" maxLength={80} editable={!loading} />
    </Card>
    <Card>
      <SectionTitle>Cambiar contraseña</SectionTitle><Text style={sharedStyles.caption}>Deja estos dos campos vacíos para conservar tu contraseña.</Text>
      <Field label="Nueva contraseña" placeholder="Al menos 10 caracteres" value={contrasena} onChangeText={setContrasena} secureTextEntry autoCapitalize="none" autoComplete="new-password" maxLength={256} editable={!loading} />
      <Field label="Confirmar nueva contraseña" value={confirmacion} onChangeText={setConfirmacion} secureTextEntry autoCapitalize="none" autoComplete="new-password" maxLength={256} editable={!loading} />
    </Card>
    {sensible && <Card><SectionTitle>Confirma tu identidad</SectionTitle><Text style={sharedStyles.caption}>Para cambiar tu correo, teléfono, usuario o contraseña, confirma tu contraseña actual.</Text><Field label="Contraseña actual" value={actual} onChangeText={setActual} secureTextEntry autoCapitalize="none" autoComplete="current-password" maxLength={256} editable={!loading} /></Card>}
    <Notice message={error} /><Notice message={aviso} tone="success" />
    <Button label="Guardar cambios" loading={loading} onPress={() => void guardar()} />
    {usuario?.rol === 'admin' && usuario.estado_acceso === 'aceptado' && <Button label="Configurar organización" variant="secondary" onPress={() => router.push('/organizacion' as Href)} />}
  </Screen>;
}

type Miembro = { id: number; usuario: { id: number; nombre_completo: string; usuario: string; correo: string }; rol: Rol };

export function OrganizacionScreen() {
  const { usuario, comprobarSesion } = useSession();
  const admin = usuario?.rol === 'admin' && usuario.estado_acceso === 'aceptado';
  const [nombre, setNombre] = useState(usuario?.organizacion?.nombre || '');
  const [descripcion, setDescripcion] = useState(usuario?.organizacion?.descripcion || '');
  const [busqueda, setBusqueda] = useState('');
  const [buscar, setBuscar] = useState('');
  const [confirmar, setConfirmar] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [aviso, setAviso] = useState('');
  const bloqueo = useRef(false);
  const { datos, cargando, error: errorConsulta, recargar } = useConsulta<{ miembros: Miembro[] }>(admin ? `organizacion/miembros/?buscar=${encodeURIComponent(buscar)}` : null);
  async function guardar() {
    if (bloqueo.current) return;
    setError(''); setAviso('');
    if (!nombre.trim()) { setError('Escribe el nombre de la organización.'); return; }
    bloqueo.current = true; setLoading(true);
    try {
      await peticionSistema('organizacion/', { metodo: 'PATCH', datos: { nombre: nombre.trim(), descripcion: descripcion.trim() } });
      await comprobarSesion(); setAviso('Los datos de la organización se guardaron.');
    } catch (err) { setError(errorTexto(err)); }
    finally { bloqueo.current = false; setLoading(false); }
  }
  async function eliminar(miembro: Miembro) {
    if (bloqueo.current) return;
    bloqueo.current = true; setLoading(true); setError(''); setAviso('');
    try {
      await peticionSistema(`organizacion/miembros/${miembro.id}/`, { metodo: 'DELETE' });
      setConfirmar(null); setAviso(`${miembro.usuario.nombre_completo} ya no tiene acceso a la organización.`); await recargar();
    } catch (err) { setError(errorTexto(err)); }
    finally { bloqueo.current = false; setLoading(false); }
  }
  function consultar() { const valor = busqueda.trim(); setConfirmar(null); if (valor === buscar) void recargar(); else setBuscar(valor); }
  return <Screen title="Configuración de organización" subtitle="Actualiza los datos de tu empresa y administra sus integrantes." refreshing={cargando} onRefresh={loading ? undefined : recargar}>
    {!admin ? <Notice message="Necesitas el rol de administrador para configurar la organización." /> : <>
      <Card><SectionTitle>Datos de la organización</SectionTitle><Field label="Nombre" value={nombre} onChangeText={setNombre} maxLength={120} editable={!loading} /><Field label="Descripción" value={descripcion} onChangeText={setDescripcion} multiline maxLength={2000} editable={!loading} /><Button label="Guardar organización" loading={loading} onPress={() => void guardar()} /></Card>
      <Notice message={error || errorConsulta} /><Notice message={aviso} tone="success" />
      <Card><SectionTitle>Miembros</SectionTitle><Field label="Buscar por nombre o usuario" placeholder="Nombre del integrante" value={busqueda} onChangeText={setBusqueda} maxLength={150} editable={!loading} onSubmitEditing={consultar} returnKeyType="search" /><Button label="Buscar miembros" variant="secondary" icon="search-outline" onPress={consultar} disabled={loading || cargando} /></Card>
      {cargando && !datos && <ActivityIndicator color={colors.primary} />}
      {datos && (datos.miembros.length ? datos.miembros.map(item => <Card key={item.id}><SectionTitle>{item.usuario.nombre_completo}</SectionTitle><Text style={sharedStyles.body}>@{item.usuario.usuario}</Text><Text style={sharedStyles.caption}>{item.usuario.correo}</Text><Text style={sharedStyles.caption}>ID de miembro: {item.id}</Text><Chip label={nombreRol(item.rol)} />
        {item.usuario.id === usuario?.id ? <Text style={sharedStyles.caption}>Esta es tu cuenta.</Text> : confirmar === item.id ? <><Notice tone="info" message="Al eliminar a este miembro perderá acceso a los módulos de la organización. Su cuenta seguirá disponible para volver a solicitar acceso." /><Button label={`Confirmar eliminación de ${item.usuario.usuario}`} variant="danger" loading={loading} onPress={() => void eliminar(item)} /><Button label="Cancelar" variant="secondary" disabled={loading} onPress={() => setConfirmar(null)} /></> : <Button label="Eliminar miembro" variant="secondary" disabled={loading} onPress={() => { setConfirmar(item.id); setError(''); }} />}
      </Card>) : <Empty message="No encontramos integrantes para esa búsqueda." />)}
      <Button label="Gestionar solicitudes de acceso" variant="secondary" onPress={() => router.push('/accesos' as Href)} />
    </>}
  </Screen>;
}
