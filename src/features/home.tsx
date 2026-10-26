import Ionicons from '@expo/vector-icons/Ionicons';
import { LinearGradient } from 'expo-linear-gradient';
import { router, type Href } from 'expo-router';
import { useState, type ComponentProps } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button, Card, Notice, Row, Screen, SectionTitle, colors, sharedStyles } from '@/components/meg';
import { useSession } from '@/context/session';
import { nombresRol, puedeAcceder, type Area } from '@/services/access';

type Module = { title: string; description: string; icon: ComponentProps<typeof Ionicons>['name']; href: Href; color?: string };
export function ModuleCards({ modules }: { modules: Module[] }) {
  return <View style={styles.moduleList}>{modules.map(module => <Pressable key={module.title} accessibilityRole="button" accessibilityLabel={module.title} onPress={() => router.push(module.href)} style={({ pressed }) => [styles.module, pressed && { opacity: 0.75 }]}>
    <View style={[styles.moduleIcon, { backgroundColor: `${module.color || colors.primary}12` }]}><Ionicons name={module.icon} size={25} color={module.color || colors.primary} /></View><View style={styles.moduleCopy}><Text style={styles.moduleTitle}>{module.title}</Text><Text style={styles.moduleDescription}>{module.description}</Text></View><Ionicons name="chevron-forward" size={19} color="#93A5BE" />
  </Pressable>)}</View>;
}

const modulos: (Module & { area: Area })[] = [
  { area: 'crm', title: 'CRM', description: 'Prospectos, clientes y nuevas ventas.', icon: 'people-outline', href: '/crm' as Href },
  { area: 'proyectos', title: 'Proyectos', description: 'Del primer requerimiento a la entrega.', icon: 'layers-outline', href: '/proyectos' as Href, color: '#7452C8' },
  { area: 'finanzas', title: 'Finanzas', description: 'Cobros, gastos y resultados de tu equipo.', icon: 'wallet-outline', href: '/finanzas' as Href, color: '#168564' },
];

export function HomeScreen() {
  const { usuario, cerrarSesion, error: sessionError, comprobarSesion } = useSession();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const activo = usuario?.estado_acceso === 'aceptado';
  const pendiente = usuario?.estado_acceso === 'pendiente';
  const estado = usuario?.estado_acceso;
  async function salir() { setLoading(true); setError(''); try { await cerrarSesion(); } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo cerrar la sesión.'); } finally { setLoading(false); } }
  return <View style={styles.home}><LinearGradient colors={['#0A162C', '#143C6D']} style={styles.homeHeader}><SafeAreaView edges={['top', 'left', 'right']}>
    <View style={styles.topbar}><Text style={styles.logo}>PROYECTOS<Text style={{ color: '#74AFFF' }}>.</Text></Text><View style={styles.role}><View style={styles.onlineDot} /><Text style={styles.roleText}>{activo ? nombresRol[usuario?.rol || ''] : pendiente ? 'Acceso pendiente' : 'Tu cuenta'}</Text></View></View>
    <Text style={styles.greeting}>Hola, {usuario?.nombre_completo.split(' ')[0] || usuario?.usuario}</Text><Text style={styles.welcome}>{activo ? usuario?.organizacion?.nombre : 'Tu próximo proyecto empieza aquí.'}</Text>
    <Text style={styles.date}>{new Intl.DateTimeFormat('es-MX', { dateStyle: 'full', timeZone: 'America/Mexico_City' }).format(new Date())}</Text>
  </SafeAreaView></LinearGradient>
    <Screen title={activo ? 'Tu espacio de trabajo' : pendiente ? 'Solicitud enviada' : 'Elige tu organización'} subtitle={activo ? 'Todo lo que necesitas para seguir avanzando.' : pendiente ? 'Tu administrador revisará la solicitud y asignará tu rol.' : 'Crea un equipo o solicita acceso a una empresa.'}>
      {activo ? <ModuleCards modules={modulos.filter(modulo => puedeAcceder(usuario, modulo.area))} /> : <Card>
        <Ionicons name={pendiente ? 'time-outline' : 'business-outline'} size={30} color={colors.primary} />
        <SectionTitle>{pendiente ? usuario?.organizacion?.nombre : estado === 'eliminado' ? 'Tu acceso fue retirado' : estado === 'rechazado' ? 'Solicitud no aprobada' : 'Trabaja con tu equipo'}</SectionTitle>
        <Text style={sharedStyles.body}>{pendiente ? 'Al aceptar tu solicitud, el administrador habilitará el módulo que te corresponda.' : 'Puedes crear una organización como administrador o buscar una organización existente para colaborar.'}</Text>
        {pendiente ? <Button label="Comprobar estado de acceso" icon="refresh-outline" onPress={() => void comprobarSesion()} /> : <Button label="Crear o unirme a una organización" icon="add-outline" onPress={() => router.push('/organizaciones' as Href)} />}
      </Card>}
      {activo && usuario?.rol === 'admin' && <ModuleCards modules={[
        { title: 'Gestionar accesos', description: 'Revisa solicitudes y asigna un rol.', icon: 'shield-checkmark-outline', href: '/accesos' as Href },
        { title: 'Organización', description: 'Configura tu empresa y administra miembros.', icon: 'business-outline', href: '/organizacion' as Href },
      ]} />}
      <Card><Row><Ionicons name="person-circle-outline" size={21} color={colors.primary} /><SectionTitle>Configuración de cuenta</SectionTitle></Row><Text style={sharedStyles.body}>{usuario?.nombre_completo}</Text><Text style={sharedStyles.caption}>{usuario?.correo}</Text><Button label="Editar mis datos" variant="secondary" onPress={() => router.push('/cuenta' as Href)} /></Card>
      <Notice message={error || sessionError} />{Boolean(sessionError) && <Button label="Reintentar conexión" onPress={() => void comprobarSesion()} variant="secondary" />}<Button label="Cerrar sesión" icon="log-out-outline" variant="secondary" loading={loading} onPress={() => void salir()} />
    </Screen>
  </View>;
}

export function ModuleScreen({ area }: { area: Area }) {
  const { usuario } = useSession();
  const modules: Record<Area, Module[]> = {
    crm: [
      { title: 'Dashboard CRM', description: 'Ventas, conversión y oportunidades del equipo.', icon: 'analytics-outline', href: '/crm/dashboard' as Href },
      { title: 'Registro de clientes', description: 'Registra prospectos y actualiza tus ventas.', icon: 'person-add-outline', href: '/crm/clientes' as Href },
    ],
    proyectos: [
      { title: 'Requerimientos', description: 'Define el alcance de tus nuevos proyectos.', icon: 'list-outline', href: '/proyectos/pendientes' as Href },
      { title: 'Gestión de proyectos', description: 'Consulta y actualiza el tablero de trabajo.', icon: 'albums-outline', href: '/proyectos/gestion' as Href },
    ],
    finanzas: [
      { title: 'Dashboard financiero', description: 'Ingresos, egresos y resultados del mes.', icon: 'bar-chart-outline', href: '/finanzas/dashboard' as Href },
      { title: 'Cobros de ventas', description: 'Registra anticipos y liquidaciones.', icon: 'cash-outline', href: '/finanzas/cobros' as Href },
      { title: 'Gastos operativos', description: 'Administra tus gastos recurrentes.', icon: 'receipt-outline', href: '/finanzas/gastos' as Href },
      { title: 'Reportes financieros', description: 'Resultados, balance y flujo de efectivo.', icon: 'documents-outline', href: '/finanzas/reportes' as Href },
    ],
  };
  return <Screen title={area === 'crm' ? 'Relaciones que crecen' : area === 'proyectos' ? 'De la idea a la entrega' : 'Tus números, claros'} subtitle={usuario?.organizacion?.nombre}>
    {puedeAcceder(usuario, area) ? <ModuleCards modules={modules[area]} /> : <Notice message="Tu cuenta no tiene acceso a este módulo." />}
    <Button label="Volver al inicio" variant="secondary" icon="home-outline" onPress={() => router.replace('/' as Href)} />
  </Screen>;
}

const styles = StyleSheet.create({
  home: { flex: 1, backgroundColor: colors.background }, homeHeader: { padding: 24, paddingBottom: 25 }, topbar: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, justifyContent: 'space-between', alignItems: 'center', marginBottom: 25 }, logo: { fontSize: 21, color: '#FFF', fontWeight: '900', letterSpacing: -0.8 }, role: { flexDirection: 'row', gap: 7, alignItems: 'center', borderColor: '#FFFFFF25', borderWidth: 1, borderRadius: 20, paddingVertical: 8, paddingHorizontal: 12 }, onlineDot: { height: 5, width: 5, borderRadius: 3, backgroundColor: '#7ADDB6' }, roleText: { color: '#C9DCF6', fontSize: 10, fontWeight: '600' }, greeting: { fontSize: 29, color: '#FFF', fontWeight: '800', letterSpacing: -0.6 }, welcome: { color: '#BBD3F2', fontSize: 15, marginTop: 9 }, date: { fontSize: 11, color: '#88A9D1', marginTop: 18, textTransform: 'capitalize' },
  moduleList: { gap: 12 }, module: { backgroundColor: colors.white, borderColor: colors.border, borderWidth: 1, borderRadius: 19, padding: 19, flexDirection: 'row', gap: 15, alignItems: 'center', minHeight: 97 }, moduleIcon: { height: 51, width: 51, borderRadius: 16, alignItems: 'center', justifyContent: 'center' }, moduleCopy: { flex: 1, gap: 5 }, moduleTitle: { color: colors.ink, fontSize: 17, fontWeight: '700' }, moduleDescription: { color: colors.muted, fontSize: 12, lineHeight: 18 },
});
