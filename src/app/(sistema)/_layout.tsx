import { Stack } from 'expo-router';
import { colors } from '@/components/meg';
export default function SistemaLayout() {
  return <Stack screenOptions={{ headerStyle: { backgroundColor: '#0C1930' }, headerTintColor: colors.white, headerTitle: 'MEG  /  Sistema interno', headerBackButtonDisplayMode: 'minimal', contentStyle: { backgroundColor: colors.background } }}><Stack.Screen name="index" options={{ headerShown: false }} /></Stack>;
}
