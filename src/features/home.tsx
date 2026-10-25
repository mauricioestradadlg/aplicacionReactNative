import Ionicons from '@expo/vector-icons/Ionicons';
import { LinearGradient } from 'expo-linear-gradient';
import { router, type Href } from 'expo-router';
import { useState, type ComponentProps } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button, Card, Notice, Row, Screen, SectionTitle, colors, sharedStyles } from '@/components/meg';
import { useSession } from '@/context/session';

type Module = { title: string; description: string; icon: ComponentProps<typeof Ionicons>['name']; href: Href; color?: string };
export function ModuleCards({ modules }: { modules: Module[] }) {
  return <View style={styles.moduleList}>{modules.map(module => <Pressable key={module.title} accessibilityRole="button" accessibilityLabel={module.title} onPress={() => router.push(module.href)} style={({ pressed }) => [styles.module, pressed && { opacity: 0.75 }]}>
    <View style={[styles.moduleIcon, { backgroundColor: `${module.color || colors.primary}12` }]}><Ionicons name={module.icon} size={25} color={module.color || colors.primary} /></View><View style={styles.moduleCopy}><Text style={styles.moduleTitle}>{module.title}</Text><Text style={styles.moduleDescription}>{module.description}</Text></View><Ionicons name="chevron-forward" size={19} color="#93A5BE" />
  </Pressable>)}</View>;
}

export function HomeScreen() {
  const { usuario, cerrarSesion, error: sessionError, comprobarSesion } = useSession();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  async function salir() { setLoading(true); setError(''); try { await cerrarSesion(); } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo cerrar la sesión.'); } finally { setLoading(false); } }
  return <View style={styles.home}><LinearGradient colors={['#0A162C', '#143C6D']} style={styles.homeHeader}><SafeAreaView edges={['top', 'left', 'right']}>
    <View style={styles.topbar}><Text style={styles.logo}>MEG<Text style={{ color: '#74AFFF' }}>.</Text></Text><View style={styles.role}><View style={styles.onlineDot} /><Text style={styles.roleText}>{usuario?.rol === 'admin' ? 'Administrador' : 'Colaborador'}</Text></View></View>
    <Text style={styles.greeting}>Hola, {usuario?.nombre_completo.split(' ')[0] || usuario?.usuario}</Text><Text style={styles.welcome}>Hagamos que las cosas pasen.</Text><Text style={styles.date}>{new Intl.DateTimeFormat('es-MX', { dateStyle: 'full' }).format(new Date())}</Text>
  </SafeAreaView></LinearGradient>
    <Screen title="Tu espacio de trabajo" subtitle="Todo lo que necesitas para seguir avanzando.">
      <ModuleCards modules={[
        { title: 'CRM', description: 'Conecta, acompaña y convierte clientes.', icon: 'people-outline', href: '/crm' as Href },
        { title: 'Proyectos', description: 'Del primer requerimiento a la entrega.', icon: 'layers-outline', href: '/proyectos' as Href, color: '#7452C8' },
        { title: 'Finanzas', description: 'Una visión clara de tus números.', icon: 'wallet-outline', href: '/finanzas' as Href, color: '#168564' },
      ]} />
      <Card><Row><Ionicons name="shield-checkmark-outline" size={19} color={colors.primary} /><SectionTitle>Una sola fuente de información</SectionTitle></Row><Text style={sharedStyles.body}>Los cambios guardados aquí también se reflejan en tu sistema web.</Text><Text style={sharedStyles.caption}>{usuario?.nombre_completo} · {usuario?.correo}</Text></Card>
      <Notice message={error || sessionError} />{Boolean(sessionError) && <Button label="Reintentar conexión" onPress={() => void comprobarSesion()} variant="secondary" />}<Button label="Cerrar sesión" icon="log-out-outline" variant="secondary" loading={loading} onPress={() => void salir()} />
    </Screen>
  </View>;
}

export function ModuleScreen({ area }: { area: 'crm' | 'proyectos' | 'finanzas' }) {
  const { usuario } = useSession();
  const modules: Record<typeof area, Module[]> = {
    crm: [
      { title: 'Dashboard CRM', description: 'Indicadores y embudo comercial.', icon: 'analytics-outline', href: '/crm/dashboard' as Href },
      { title: 'Prospectos', description: 'Registro y seguimiento de oferta de valor.', icon: 'person-add-outline', href: '/crm/prospectos' as Href },
      { title: 'Clientes potenciales', description: 'Califica oportunidades y agenda citas.', icon: 'calendar-outline', href: '/crm/potenciales' as Href },
      { title: 'Lead Magnet', description: 'Registros de tus campañas y plantillas.', icon: 'magnet-outline', href: '/crm/leads' as Href },
      { title: 'Email Marketing', description: 'Tips, feedback y oportunidades comerciales.', icon: 'mail-outline', href: '/crm/email' as Href },
      { title: 'Cierre de ventas', description: 'Citas, cotizaciones y conversiones.', icon: 'checkmark-done-outline', href: '/crm/cierre' as Href },
      { title: 'Gestión de ventas', description: 'Importes, anticipos y liquidaciones.', icon: 'briefcase-outline', href: '/crm/ventas' as Href },
      { title: 'Crear cotización', description: 'Calcula tu propuesta y comparte el PDF.', icon: 'document-text-outline', href: '/crm/cotizacion' as Href },
      { title: 'Aprobar reseñas', description: 'Revisa los testimonios de tus clientes.', icon: 'star-outline', href: '/crm/resenas' as Href },
    ],
    proyectos: [
      { title: 'Requerimientos', description: 'Define el alcance de tus nuevos proyectos.', icon: 'list-outline', href: '/proyectos/pendientes' as Href },
      { title: 'Gestión de proyectos', description: 'Consulta y actualiza el tablero de trabajo.', icon: 'albums-outline', href: '/proyectos/gestion' as Href },
    ],
    finanzas: [
      { title: 'Dashboard financiero', description: 'Ingresos, egresos y resultados del mes.', icon: 'bar-chart-outline', href: '/finanzas/dashboard' as Href },
      { title: 'Gastos operativos', description: 'Administra tus gastos recurrentes.', icon: 'receipt-outline', href: '/finanzas/gastos' as Href },
      { title: 'Reportes financieros', description: 'Resultados, balance y flujo de efectivo.', icon: 'documents-outline', href: '/finanzas/reportes' as Href },
    ],
  };
  return <Screen title={area === 'crm' ? 'Relaciones que crecen' : area === 'proyectos' ? 'De la idea a la entrega' : 'Tus números, claros'} subtitle={area === 'crm' ? 'Marketing y ventas · CRM' : area === 'proyectos' ? 'Organiza el trabajo de cada proyecto.' : 'Información financiera de tu operación.'}>{usuario?.rol === 'admin' ? <ModuleCards modules={modules[area]} /> : <Card><SectionTitle>Acceso de administrador</SectionTitle><Text style={sharedStyles.body}>Tu cuenta está activa. Estas funciones requieren el rol de administrador, igual que en el sistema web.</Text></Card>}</Screen>;
}

const styles = StyleSheet.create({
  home: { flex: 1, backgroundColor: colors.background }, homeHeader: { padding: 25, paddingBottom: 27 }, topbar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 30 }, logo: { fontSize: 29, color: '#FFF', fontWeight: '900', letterSpacing: -1.5 }, role: { flexDirection: 'row', gap: 7, alignItems: 'center', borderColor: '#FFFFFF25', borderWidth: 1, borderRadius: 20, paddingVertical: 8, paddingHorizontal: 12 }, onlineDot: { height: 5, width: 5, borderRadius: 3, backgroundColor: '#7ADDB6' }, roleText: { color: '#C9DCF6', fontSize: 10, fontWeight: '600' }, greeting: { fontSize: 29, color: '#FFF', fontWeight: '800', letterSpacing: -0.6 }, welcome: { color: '#BBD3F2', fontSize: 14, marginTop: 9 }, date: { fontSize: 11, color: '#88A9D1', marginTop: 18, textTransform: 'capitalize' },
  moduleList: { gap: 12 }, module: { backgroundColor: colors.white, borderColor: colors.border, borderWidth: 1, borderRadius: 19, padding: 19, flexDirection: 'row', gap: 15, alignItems: 'center', minHeight: 97 }, moduleIcon: { height: 51, width: 51, borderRadius: 16, alignItems: 'center', justifyContent: 'center' }, moduleCopy: { flex: 1, gap: 5 }, moduleTitle: { color: colors.ink, fontSize: 17, fontWeight: '700' }, moduleDescription: { color: colors.muted, fontSize: 12, lineHeight: 18 },
});
