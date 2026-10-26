import { Stack } from 'expo-router';
import { colors } from '@/components/meg';
import { useSession } from '@/context/session';
import { puedeAcceder } from '@/services/access';

export default function SistemaLayout() {
  const { usuario } = useSession();
  const admin = usuario?.estado_acceso === 'aceptado' && usuario.rol === 'admin';
  return <Stack key={`${usuario?.organizacion?.id}:${usuario?.rol}:${usuario?.estado_acceso}`} screenOptions={{ headerStyle: { backgroundColor: '#0C1930' }, headerTintColor: colors.white, headerTitle: usuario?.organizacion?.nombre || 'Tu espacio de trabajo', headerBackButtonDisplayMode: 'minimal', contentStyle: { backgroundColor: colors.background } }}>
    <Stack.Screen name="index" options={{ headerShown: false }} />
    <Stack.Screen name="cuenta" options={{ title: 'Mi cuenta' }} />
    <Stack.Protected guard={usuario?.estado_acceso !== 'aceptado' && usuario?.estado_acceso !== 'pendiente'}><Stack.Screen name="organizaciones" options={{ title: 'Organizaciones' }} /></Stack.Protected>
    <Stack.Protected guard={admin}><Stack.Screen name="accesos" options={{ title: 'Gestionar accesos' }} /><Stack.Screen name="organizacion" options={{ title: 'Organización' }} /></Stack.Protected>
    <Stack.Protected guard={puedeAcceder(usuario, 'crm')}><Stack.Screen name="crm" /></Stack.Protected>
    <Stack.Protected guard={puedeAcceder(usuario, 'proyectos')}><Stack.Screen name="proyectos" /></Stack.Protected>
    <Stack.Protected guard={puedeAcceder(usuario, 'finanzas')}><Stack.Screen name="finanzas" /></Stack.Protected>
  </Stack>;
}
