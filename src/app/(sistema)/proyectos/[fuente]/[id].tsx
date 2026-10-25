import { useLocalSearchParams } from 'expo-router';
import { ProyectoDetalleScreen } from '@/features/projects/screens';
export default function Detalle() {
  const params = useLocalSearchParams<{ fuente: string; id: string; vista?: string }>();
  return <ProyectoDetalleScreen fuente={params.fuente || ''} id={params.id || ''} tablero={params.vista === 'tablero'} />;
}
