import type { Usuario } from '@/context/session';

export type Area = 'crm' | 'proyectos' | 'finanzas';
export const nombresRol: Record<string, string> = { admin: 'Administrador', desarrollador: 'Desarrollador', crm: 'CRM', finanzas: 'Finanzas' };
export function puedeAcceder(usuario: Usuario | null, area: Area) {
  return Boolean(usuario?.estado_acceso === 'aceptado' && usuario.organizacion && (usuario.rol === 'admin' || usuario.rol === (area === 'proyectos' ? 'desarrollador' : area)));
}
