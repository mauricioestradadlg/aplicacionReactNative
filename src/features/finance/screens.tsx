import { useRef, useState } from 'react';
import { router, type Href } from 'expo-router';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Button, Card, Chip, Empty, Field, Notice, Row, Screen, SectionTitle, Stat, colors, sharedStyles } from '@/components/meg';
import { useSession } from '@/context/session';
import { useConsulta } from '@/hooks/use-consulta';
import { peticionSistema } from '@/services/api';
import { puedeAcceder } from '@/services/access';

type Importe = string | number | null;
type Gasto = { id: string; concepto: string; monto_mensual: string };
type BorradorGasto = { concepto: string; monto_mensual: string };
type GastosRespuesta = { gastos: Gasto[]; total_mensual: string; mensaje?: string };
type Resumen = { cobros_mes: Importe; gastos_mes: Importe; resultado_operativo: Importe; anticipos_mes: Importe; saldos_mes: Importe; margen_operativo_pct: Importe; cobertura_gastos_pct: Importe; variacion_cobros_pct: Importe };
type Mes = { mes: string; cobros_mes: Importe; gastos_mes: Importe; resultado_operativo: Importe };
type DashboardRespuesta = {
  periodo: string; resumen: Resumen; tendencia: Mes[];
  comparativo: { periodo: string; cobros_mes: Importe; gastos_mes: Importe; resultado_operativo: Importe } | null;
  gastos: { id: string; concepto: string; monto: Importe }[];
  advertencias: string[]; alcance: string; ventas_sin_importes: number;
  inicio_historial_gastos: string | null; actualizado_en: string;
};
type TipoReporte = 'estado-resultados' | 'balance-general' | 'flujo-efectivo';
type ReporteRespuesta = {
  tipo: TipoReporte; periodo: string; alcance: string; pendientes: string;
  advertencias: string[]; ventas_sin_importes: number; inicio_historial_gastos: string | null;
  lineas: { clave: string; concepto: string; importe: Importe; tipo: string }[];
};

const reportes: { tipo: TipoReporte; titulo: string }[] = [
  { tipo: 'estado-resultados', titulo: 'Estado de resultados' },
  { tipo: 'balance-general', titulo: 'Balance general' },
  { tipo: 'flujo-efectivo', titulo: 'Flujo de efectivo' },
];
const dinero = new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' });
const importe = (valor: Importe | undefined) => valor == null || !Number.isFinite(Number(valor)) ? '—' : dinero.format(Number(valor));
const porcentaje = (valor: Importe) => valor == null || !Number.isFinite(Number(valor)) ? '—' : `${new Intl.NumberFormat('es-MX', { maximumFractionDigits: 2 }).format(Number(valor))}%`;
const actual = () => {
  const partes = new Intl.DateTimeFormat('en', { timeZone: 'America/Mexico_City', year: 'numeric', month: '2-digit' }).formatToParts(new Date());
  return `${partes.find((parte) => parte.type === 'year')?.value}-${partes.find((parte) => parte.type === 'month')?.value}`;
};
const nombreMes = (periodo: string) => /^\d{4}-(0[1-9]|1[0-2])$/.test(periodo) ? new Intl.DateTimeFormat('es-MX', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${periodo}-01T12:00:00Z`)) : periodo;
const errorTexto = (error: unknown) => error instanceof Error ? error.message : 'No fue posible guardar el gasto. Tus cambios se conservan.';

function Periodo({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [texto, setTexto] = useState(value);
  const [error, setError] = useState('');
  function consultar() {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(texto) || texto < '1900-01' || texto > actual()) {
      setError('Escribe un mes válido, desde 1900-01 hasta el mes actual, en formato AAAA-MM.'); return;
    }
    setError(''); onChange(texto);
  }
  function desplazar(cantidad: number) {
    const [anio, mes] = value.split('-').map(Number);
    const fecha = new Date(Date.UTC(anio, mes - 1 + cantidad, 1));
    const siguiente = `${fecha.getUTCFullYear()}-${String(fecha.getUTCMonth() + 1).padStart(2, '0')}`;
    if (siguiente < '1900-01' || siguiente > actual()) return;
    setTexto(siguiente); setError(''); onChange(siguiente);
  }
  return <Card>
    <Field label="Periodo (AAAA-MM)" value={texto} onChangeText={setTexto} placeholder="2026-10" maxLength={7} autoCapitalize="none" returnKeyType="search" onSubmitEditing={consultar} />
    {error ? <Notice message={error} /> : null}
    <Row>
      <Button label="Mes anterior" variant="secondary" onPress={() => desplazar(-1)} disabled={value <= '1900-01'} />
      <Button label="Consultar" onPress={consultar} />
      <Button label="Mes siguiente" variant="secondary" onPress={() => desplazar(1)} disabled={value >= actual()} />
    </Row>
    <Text style={sharedStyles.caption}>{nombreMes(value)} · Pesos mexicanos (MXN)</Text>
  </Card>;
}

function Advertencias({ advertencias, ventas }: { advertencias: string[]; ventas: number }) {
  return <>
    {advertencias.map((mensaje) => <Notice key={mensaje} message={mensaje} tone="info" />)}
    {ventas > 0 ? <Button label="Completar importes de ventas" variant="secondary" onPress={() => router.push('/finanzas/cobros' as Href)} /> : null}
  </>;
}

function FilaImporte({ label, valor, total = false }: { label: string; valor: Importe; total?: boolean }) {
  return <View style={[styles.amountRow, total && styles.amountTotal]}>
    <Text style={[styles.amountLabel, total && styles.bold]}>{label}</Text>
    <Text style={[styles.amountValue, total && styles.bold]}>{importe(valor)}</Text>
  </View>;
}

export function DashboardFinanzasScreen() {
  const { usuario } = useSession();
  const admin = puedeAcceder(usuario, 'finanzas');
  const [periodo, setPeriodo] = useState(actual);
  const { datos, cargando, error, recargar } = useConsulta<DashboardRespuesta>(admin ? `finanzas/dashboard/?periodo=${encodeURIComponent(periodo)}` : null);
  const resumen = datos?.periodo === periodo ? datos.resumen : null;
  const maxGrafica = Math.max(1, ...(datos?.tendencia || []).flatMap((mes) => [Number(mes.cobros_mes) || 0, Number(mes.gastos_mes) || 0]));
  return <Screen title="Dashboard financiero" subtitle="Tus cobros, gastos y resultados del mes en un solo lugar." refreshing={cargando} onRefresh={recargar}>
    {!admin ? <Notice message="Necesitas acceso a Finanzas para consultar los indicadores financieros." /> : <>
      <Periodo value={periodo} onChange={setPeriodo} />
      {error ? <><Notice message={error} /><Button label="Reintentar" variant="secondary" onPress={recargar} /></> : null}
      {cargando && !resumen ? <ActivityIndicator color={colors.primary} /> : null}
      {datos && resumen ? <>
        <Row>
          <Stat label="Ingresos cobrados" value={importe(resumen.cobros_mes)} detail="Anticipos y saldos recibidos" />
          <Stat label="Gastos operativos" value={importe(resumen.gastos_mes)} detail="Importes mensuales registrados" />
        </Row>
        <Row>
          <Stat label="Resultado operativo parcial" value={importe(resumen.resultado_operativo)} detail="Cobros menos gastos registrados" />
          <Stat label="Margen parcial" value={porcentaje(resumen.margen_operativo_pct)} detail="Resultado ÷ cobros" />
        </Row>
        <Row>
          <Stat label="Anticipos cobrados" value={importe(resumen.anticipos_mes)} />
          <Stat label="Saldos cobrados" value={importe(resumen.saldos_mes)} />
        </Row>
        <Row>
          <Stat label="Cobertura de gastos" value={porcentaje(resumen.cobertura_gastos_pct)} />
          <Stat label="Variación de cobros" value={porcentaje(resumen.variacion_cobros_pct)} detail="Frente al mes anterior" />
        </Row>
        <Advertencias advertencias={datos.advertencias || []} ventas={datos.ventas_sin_importes} />
        <Card>
          <SectionTitle>Evolución mensual</SectionTitle>
          <Text style={sharedStyles.caption}>Cobros y gastos · últimos seis meses</Text>
          <Row><Chip label="Azul: cobros" /><Chip label="Gris: gastos operativos" /></Row>
          {datos.tendencia.length ? datos.tendencia.map((mes) => <View key={mes.mes} style={styles.month}>
            <Text style={styles.monthTitle}>{nombreMes(mes.mes)}</Text>
            <View style={styles.barTrack}><View style={[styles.bar, { width: `${Math.max(0, Number(mes.cobros_mes) / maxGrafica * 100)}%` }]} /></View>
            <View style={styles.barTrack}><View style={[styles.bar, { width: `${Math.max(0, Number(mes.gastos_mes) / maxGrafica * 100)}%`, backgroundColor: '#8496B0' }]} /></View>
            <Text style={sharedStyles.caption}>Cobros {importe(mes.cobros_mes)} · Gastos {importe(mes.gastos_mes)}</Text>
            <Text style={sharedStyles.caption}>Resultado parcial {importe(mes.resultado_operativo)}</Text>
          </View>) : <Empty message="Aún no hay datos de tendencia." />}
          <Text style={sharedStyles.caption}>«—» indica información pendiente de registro.</Text>
        </Card>
        <Card>
          <SectionTitle>Gastos por concepto</SectionTitle>
          {datos.gastos.length ? datos.gastos.map((gasto) => <FilaImporte key={gasto.id} label={gasto.concepto} valor={gasto.monto} />) : <Text style={sharedStyles.body}>No hay gastos registrados para este periodo.</Text>}
          <FilaImporte label="Total mensual" valor={resumen.gastos_mes} total />
          <Button label="Administrar gastos" variant="secondary" onPress={() => router.push('/finanzas/gastos' as Href)} />
        </Card>
        {datos.comparativo ? <Card>
          <SectionTitle>Frente a {nombreMes(datos.comparativo.periodo)}</SectionTitle>
          <FilaImporte label="Ingresos cobrados anteriores" valor={datos.comparativo.cobros_mes} />
          <FilaImporte label="Gastos operativos anteriores" valor={datos.comparativo.gastos_mes} />
          <FilaImporte label="Resultado parcial anterior" valor={datos.comparativo.resultado_operativo} />
          {periodo === actual() ? <Text style={sharedStyles.caption}>Se compara el mes en curso con el mes anterior completo.</Text> : null}
        </Card> : null}
        <Notice message={datos.alcance} tone="info" />
        <Button label="Ver reportes financieros" onPress={() => router.push('/finanzas/reportes' as Href)} />
        {datos.actualizado_en ? <Text style={sharedStyles.caption}>Actualizado: {new Intl.DateTimeFormat('es-MX', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Mexico_City' }).format(new Date(datos.actualizado_en))}</Text> : null}
      </> : null}
    </>}
  </Screen>;
}

export function GastosScreen() {
  const { usuario } = useSession();
  const admin = puedeAcceder(usuario, 'finanzas');
  const { datos, cargando, error, recargar } = useConsulta<GastosRespuesta>(admin ? 'finanzas/gastos-operativos/' : null);
  const [borradores, setBorradores] = useState<Record<string, BorradorGasto>>({});
  const [nuevo, setNuevo] = useState<BorradorGasto>({ concepto: '', monto_mensual: '' });
  const [guardando, setGuardando] = useState('');
  const bloqueo = useRef(false);
  const [errorGuardado, setErrorGuardado] = useState('');
  const [aviso, setAviso] = useState('');
  function cambiar(gasto: Gasto, campo: keyof BorradorGasto, valor: string) {
    setBorradores((prev) => ({ ...prev, [gasto.id]: { ...(prev[gasto.id] || gasto), [campo]: valor } }));
    setAviso(''); setErrorGuardado('');
  }
  async function guardar(gasto?: Gasto) {
    if (bloqueo.current) return;
    const id = gasto?.id || 'nuevo';
    const valores = gasto ? borradores[id] || gasto : nuevo;
    const monto = valores.monto_mensual.trim().replace(',', '.');
    if (!valores.concepto.trim()) { setErrorGuardado('Escribe el concepto del gasto.'); return; }
    if (!/^\d+(\.\d{1,2})?$/.test(monto) || Number(monto) > 9999999999.99) { setErrorGuardado('Escribe un monto desde 0 hasta 9999999999.99 con máximo dos decimales.'); return; }
    bloqueo.current = true; setGuardando(id); setErrorGuardado(''); setAviso('');
    try {
      const respuesta = await peticionSistema<GastosRespuesta>(gasto ? `finanzas/gastos-operativos/${id}/` : 'finanzas/gastos-operativos/', { metodo: 'POST', datos: { concepto: valores.concepto.trim(), monto_mensual: monto } });
      await recargar();
      if (gasto) setBorradores((prev) => { const siguientes = { ...prev }; delete siguientes[id]; return siguientes; });
      else setNuevo({ concepto: '', monto_mensual: '' });
      setAviso(respuesta.mensaje || 'Gasto guardado correctamente.');
    } catch (err) { setErrorGuardado(errorTexto(err)); }
    finally { bloqueo.current = false; setGuardando(''); }
  }
  return <Screen title="Gastos operativos" subtitle="Administra el costo mensual de operar tu negocio." refreshing={cargando} onRefresh={guardando ? undefined : recargar}>
    {!admin ? <Notice message="Necesitas acceso a Finanzas para consultar y modificar los gastos operativos." /> : <>
      <Notice message="Los cambios aplican al mes en curso y a los siguientes. El historial de meses anteriores se conserva." tone="info" />
      {error || errorGuardado ? <Notice message={errorGuardado || error} /> : null}
      {error ? <Button label="Reintentar consulta" variant="secondary" onPress={recargar} /> : null}
      {aviso ? <Notice message={aviso} tone="success" /> : null}
      {cargando && !datos ? <ActivityIndicator color={colors.primary} /> : null}
      {datos ? <>
        <Stat label="Costo total por mes" value={importe(datos.total_mensual)} detail={`${datos.gastos.length} conceptos registrados · MXN`} />
        {datos.gastos.length === 0 ? <Empty message="Todavía no hay gastos registrados. Añade el primero." /> : datos.gastos.map((gasto) => {
          const valores = borradores[gasto.id] || gasto;
          return <Card key={gasto.id}>
            <Field label="Concepto" value={valores.concepto} onChangeText={(valor) => cambiar(gasto, 'concepto', valor)} maxLength={150} editable={!guardando} />
            <Field label="Monto mensual (MXN)" value={valores.monto_mensual} onChangeText={(valor) => cambiar(gasto, 'monto_mensual', valor)} keyboardType="decimal-pad" editable={!guardando} />
            <Button label="Guardar cambios" variant="secondary" onPress={() => guardar(gasto)} disabled={Boolean(guardando) || !borradores[gasto.id]} loading={guardando === gasto.id} />
          </Card>;
        })}
      </> : null}
      <Card>
        <SectionTitle>Añadir gasto</SectionTitle>
        <Field label="Concepto *" placeholder="Ej. Hosting, herramientas, internet" value={nuevo.concepto} onChangeText={(concepto) => setNuevo((prev) => ({ ...prev, concepto }))} maxLength={150} editable={!guardando} />
        <Field label="Monto mensual (MXN) *" placeholder="0.00" value={nuevo.monto_mensual} onChangeText={(monto_mensual) => setNuevo((prev) => ({ ...prev, monto_mensual }))} keyboardType="decimal-pad" editable={!guardando} />
        <Button label="Añadir y guardar" onPress={() => guardar()} loading={guardando === 'nuevo'} disabled={Boolean(guardando)} />
      </Card>
    </>}
  </Screen>;
}

export function ReportesScreen() {
  const { usuario } = useSession();
  const admin = puedeAcceder(usuario, 'finanzas');
  const [periodo, setPeriodo] = useState(actual);
  const [tipo, setTipo] = useState<TipoReporte>('estado-resultados');
  const params = new URLSearchParams({ periodo, tipo });
  const { datos, cargando, error, recargar } = useConsulta<ReporteRespuesta>(admin ? `finanzas/reportes/?${params}` : null);
  const vigente = datos?.periodo === periodo && datos?.tipo === tipo ? datos : null;
  return <Screen title="Reportes financieros" subtitle="Consulta los movimientos e indicadores registrados en tu sistema." refreshing={cargando} onRefresh={recargar}>
    {!admin ? <Notice message="Necesitas acceso a Finanzas para consultar los reportes financieros." /> : <>
      <Row>{reportes.map((reporte) => <Chip key={reporte.tipo} label={reporte.titulo} selected={tipo === reporte.tipo} onPress={() => setTipo(reporte.tipo)} />)}</Row>
      <Periodo value={periodo} onChange={setPeriodo} />
      {error ? <><Notice message={error} /><Button label="Reintentar" variant="secondary" onPress={recargar} /></> : null}
      {cargando && !vigente ? <ActivityIndicator color={colors.primary} /> : null}
      {vigente ? <>
        <Card>
          <SectionTitle>{reportes.find((reporte) => reporte.tipo === tipo)?.titulo}</SectionTitle>
          <Text style={sharedStyles.caption}>{nombreMes(vigente.periodo)} · MXN</Text>
          {vigente.lineas.map((linea) => <FilaImporte key={linea.clave} label={linea.concepto} valor={linea.importe} total={linea.tipo === 'total'} />)}
        </Card>
        <Notice message={vigente.alcance} tone="info" />
        <Advertencias advertencias={vigente.advertencias || []} ventas={vigente.ventas_sin_importes} />
        {vigente.pendientes ? <Text style={sharedStyles.caption}>{vigente.pendientes}</Text> : null}
        {vigente.inicio_historial_gastos ? <Text style={sharedStyles.caption}>Historial de gastos disponible desde {nombreMes(vigente.inicio_historial_gastos.slice(0, 7))}.</Text> : null}
      </> : null}
    </>}
  </Screen>;
}

const styles = StyleSheet.create({
  amountRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, justifyContent: 'space-between', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  amountTotal: { backgroundColor: '#EEF4FF', paddingHorizontal: 10, borderRadius: 8, borderBottomWidth: 0 },
  amountLabel: { color: colors.ink, fontSize: 14, flex: 1, lineHeight: 20 },
  amountValue: { color: colors.ink, fontSize: 14, textAlign: 'right', maxWidth: '48%', lineHeight: 20, fontVariant: ['tabular-nums'] },
  bold: { fontWeight: '700' },
  month: { gap: 7, paddingVertical: 10 },
  monthTitle: { color: colors.ink, fontWeight: '600', fontSize: 14, textTransform: 'capitalize' },
  barTrack: { backgroundColor: '#EDF1F8', height: 7, borderRadius: 5, overflow: 'hidden' },
  bar: { backgroundColor: '#176CF2', height: '100%', borderRadius: 5 },
});
