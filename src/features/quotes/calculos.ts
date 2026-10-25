export const PRECIOS = Object.freeze({ 'landing-page': 3500, 'sitio-web': 6000, formulario: 1000, funcionalidad: 2000, panel: 3000, gestionDominio: 300, iva: 0.16, mantenimiento: 0.10 });
export const DOMINIOS = Object.freeze({ '.mx': 295, '.com': 295, '.com.mx': 265 });
export const SERVICIOS = {
  'landing-page': { nombre: 'Landing Page', descripcion: 'Una sola página con la información esencial de tu negocio.', tiempo: '5 a 7 días hábiles', secciones: ['Inicio', 'Menú o productos', 'Promociones', 'Ubicación y horarios', 'Contacto y redes sociales'] },
  'sitio-web': { nombre: 'Sitio Web', descripcion: 'Varias páginas independientes para explicar y organizar la información de tu negocio.', tiempo: '10 a 14 días hábiles', secciones: ['Inicio', 'Quiénes somos', 'Menú o productos', 'Sucursales', 'Promociones o novedades', 'Contacto'] },
} as const;
export type Servicio = keyof typeof SERVICIOS;
export type Cotizacion = {
  folio: string; fecha: string; nombre: string; negocio: string; telefono: string; correo: string;
  objetivo: string; servicio: Servicio; formulario: boolean; cantidadFunciones: string | number; panel: boolean;
  funcionalidadesDetalle: string; descuento: string; dominio: string; costoDominio: string | number;
  mantenimiento: boolean; referido: boolean; notas: string;
};
export const money = (value: number | string) => new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN', minimumFractionDigits: 2 }).format(Number(value) || 0);
const pesos = (value: number) => Math.round(value * 100) / 100;

// Importes finales en MXN, IVA incluido. Misma política comercial que la web.
export function calcularCotizacion(form: Cotizacion) {
  const servicio: Servicio = Object.hasOwn(SERVICIOS, form.servicio) ? form.servicio : 'landing-page';
  const cantidadFunciones = Math.max(0, Math.min(20, Math.trunc(Number(form.cantidadFunciones) || 0)));
  const conceptos = [{ descripcion: SERVICIOS[servicio].nombre as string, cantidad: 1, unitario: PRECIOS[servicio] as number }];
  if (form.formulario) conceptos.push({ descripcion: 'Formulario de contacto / solicitudes', cantidad: 1, unitario: PRECIOS.formulario });
  if (cantidadFunciones) conceptos.push({ descripcion: 'Funcionalidad nueva (alcance a definir)', cantidad: cantidadFunciones, unitario: PRECIOS.funcionalidad });
  if (form.panel) conceptos.push({ descripcion: 'Panel administrativo', cantidad: 1, unitario: PRECIOS.panel });
  const brutoDesarrollo = pesos(conceptos.reduce((acc, item) => acc + item.cantidad * item.unitario, 0));
  const descuentoPct = form.descuento === 'plantilla' ? 0.10 : form.descuento === 'diseno' ? 0.20 : 0;
  const descuentoImporte = pesos(brutoDesarrollo * descuentoPct);
  const desarrollo = pesos(brutoDesarrollo - descuentoImporte);
  const dominioExtension = Object.hasOwn(DOMINIOS, form.dominio) ? form.dominio : '';
  const costoDominio = dominioExtension ? pesos(Math.max(0, Number(form.costoDominio) || 0)) : 0;
  const gestionDominio = dominioExtension ? PRECIOS.gestionDominio : 0;
  const totalDominio = pesos(costoDominio + gestionDominio);
  const totalInicial = pesos(desarrollo + totalDominio);
  const anticipoDesarrollo = pesos(desarrollo / 2);
  const saldoDesarrollo = pesos(desarrollo - anticipoDesarrollo);
  const primerPago = pesos(anticipoDesarrollo + totalDominio);
  const mensualidad = pesos(desarrollo * PRECIOS.mantenimiento);
  const baseSinIVA = pesos(totalInicial / (1 + PRECIOS.iva));
  const ivaIncluido = pesos(totalInicial - baseSinIVA);
  return { servicio, conceptos, brutoDesarrollo, descuentoPct, descuentoImporte, desarrollo, dominioExtension, costoDominio, gestionDominio, totalDominio, totalInicial, anticipoDesarrollo, saldoDesarrollo, primerPago, mensualidad, baseSinIVA, ivaIncluido };
}

export function fechaHoy() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Mexico_City', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const part = (name: string) => parts.find(p => p.type === name)?.value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}
export function nuevaCotizacion(): Cotizacion {
  return { folio: `COT-${fechaHoy().replaceAll('-', '')}-${String(Date.now()).slice(-5)}`, fecha: fechaHoy(), nombre: '', negocio: '', telefono: '', correo: '', objetivo: 'Presentar el negocio de manera profesional y facilitar que nuevos clientes encuentren información y puedan contactarnos.', servicio: 'landing-page', formulario: false, cantidadFunciones: '', panel: false, funcionalidadesDetalle: '', descuento: 'ninguno', dominio: '', costoDominio: '', mantenimiento: false, referido: false, notas: '' };
}
