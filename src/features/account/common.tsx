import type { Rol } from '@/context/session';
import { Chip, Row } from '@/components/meg';

export const roles: { valor: Rol; nombre: string; descripcion: string }[] = [
  { valor: 'admin', nombre: 'Administrador', descripcion: 'Todos los módulos y gestión de la organización.' },
  { valor: 'desarrollador', nombre: 'Desarrollador', descripcion: 'Requerimientos y tablero de proyectos.' },
  { valor: 'crm', nombre: 'CRM', descripcion: 'Clientes, prospectos y ventas.' },
  { valor: 'finanzas', nombre: 'Finanzas', descripcion: 'Cobros, gastos y reportes financieros.' },
];
export const nombreRol = (rol: Rol | null) => roles.find(item => item.valor === rol)?.nombre || 'Sin rol asignado';
export const errorTexto = (error: unknown) => error instanceof Error ? error.message : 'No fue posible guardar los cambios. Intenta de nuevo.';

export function Roles({ value, onChange, disabled = false }: { value: Rol; onChange: (rol: Rol) => void; disabled?: boolean }) {
  return <Row>{roles.map(rol => <Chip key={rol.valor} label={rol.nombre} selected={value === rol.valor} onPress={disabled ? undefined : () => onChange(rol.valor)} />)}</Row>;
}
