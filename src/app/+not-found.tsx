import { Link } from 'expo-router';
import { Screen, Empty } from '@/components/meg';
export default function NotFound() { return <Screen title="Página no encontrada"><Empty message="Esta pantalla no existe en el sistema." /><Link href="/">Volver al inicio</Link></Screen>; }
