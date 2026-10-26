import { useRef, useState } from 'react';
import { ActivityIndicator, Text } from 'react-native';
import { Button, Card, Chip, Empty, Notice, Screen, SectionTitle, colors, sharedStyles } from '@/components/meg';
import { useSession, type Rol } from '@/context/session';
import { useConsulta } from '@/hooks/use-consulta';
import { peticionSistema } from '@/services/api';
import { Roles, errorTexto, roles } from './common';

type Solicitud = { id: number; usuario: { id: number; usuario: string; nombre_completo: string; correo: string }; creado_en?: string };

export function AccesosScreen() {
  const { usuario } = useSession();
  const admin = usuario?.rol === 'admin' && usuario.estado_acceso === 'aceptado';
  const { datos, cargando, error, recargar } = useConsulta<{ solicitudes: Solicitud[] }>(admin ? 'organizacion/solicitudes/' : null);
  const [seleccion, setSeleccion] = useState<number | null>(null);
  const [rol, setRol] = useState<Rol>('desarrollador');
  const [guardando, setGuardando] = useState(false);
  const [errorGuardado, setErrorGuardado] = useState('');
  const [aviso, setAviso] = useState('');
  const bloqueo = useRef(false);
  async function decidir(solicitud: Solicitud, aceptar: boolean) {
    if (bloqueo.current) return;
    bloqueo.current = true; setGuardando(true); setErrorGuardado(''); setAviso('');
    try {
      await peticionSistema(`organizacion/solicitudes/${solicitud.id}/`, { metodo: 'POST', datos: { aceptar, rol } });
      setSeleccion(null); setAviso(aceptar ? `${solicitud.usuario.nombre_completo} ya puede entrar con el rol seleccionado.` : 'Solicitud rechazada. El usuario podrá volver a solicitar acceso.');
      await recargar();
    } catch (err) { setErrorGuardado(errorTexto(err)); }
    finally { bloqueo.current = false; setGuardando(false); }
  }
  return <Screen title="Gestionar accesos" subtitle="Revisa quién quiere unirse a tu organización y asigna su rol." refreshing={cargando} onRefresh={guardando ? undefined : recargar}>
    {!admin ? <Notice message="Necesitas el rol de administrador para gestionar solicitudes." /> : <>
      <Notice message={errorGuardado || error} /><Notice message={aviso} tone="success" />
      {Boolean(error) && <Button label="Reintentar" variant="secondary" onPress={recargar} />}
      {cargando && !datos && <ActivityIndicator color={colors.primary} />}
      {datos && <><SectionTitle>{datos.solicitudes.length} solicitudes pendientes</SectionTitle>{datos.solicitudes.length ? datos.solicitudes.map(item => <Card key={item.id}>
        <Chip label="Acceso pendiente" /><SectionTitle>{item.usuario.nombre_completo}</SectionTitle><Text style={sharedStyles.body}>@{item.usuario.usuario}</Text><Text style={sharedStyles.caption}>{item.usuario.correo}</Text>
        {seleccion === item.id ? <>
          <SectionTitle>Asigna un rol</SectionTitle><Roles value={rol} onChange={setRol} disabled={guardando} /><Text style={sharedStyles.caption}>{roles.find(actual => actual.valor === rol)?.descripcion}</Text>
          <Button label="Aceptar acceso y guardar rol" loading={guardando} onPress={() => void decidir(item, true)} />
          <Button label="Rechazar solicitud" variant="danger" disabled={guardando} onPress={() => void decidir(item, false)} />
          <Button label="Cerrar" variant="secondary" disabled={guardando} onPress={() => setSeleccion(null)} />
        </> : <Button label="Revisar solicitud" variant="secondary" disabled={guardando} onPress={() => { setSeleccion(item.id); setRol('desarrollador'); setErrorGuardado(''); }} />}
      </Card>) : <Empty message="No hay solicitudes pendientes. Las nuevas solicitudes de tu equipo aparecerán aquí." />}</>}
    </>}
  </Screen>;
}
