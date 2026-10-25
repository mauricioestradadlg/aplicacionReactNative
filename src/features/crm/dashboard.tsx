import { useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Button, Card, Field, Notice, Screen, SectionTitle, Stat, colors } from '@/components/meg';
import { useSession } from '@/context/session';
import { useConsulta } from '@/hooks/use-consulta';

import { money, styles } from './common';

type Dashboard = { conteos: Record<string, number>; alcance: string; tendencia: { mes: string; whatsapp: number; lead_magnet: number; citas: number }[] };
const percent = (value: number, total: number) => total > 0 ? `${(100 * value / total).toFixed(1)}%` : '—';
const cost = (spend: number, total: number) => total > 0 ? money(spend / total) : '—';
function month(value: string) {
  const date = new Date(`${value}-01T12:00:00Z`);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('es-MX', { month: 'short', year: '2-digit', timeZone: 'UTC' }).format(date);
}
function Funnel({ label, value, max }: { label: string; value: number; max: number }) {
  return <View style={chart.funnel}><View style={chart.legend}><Text style={styles.body}>{label}</Text><Text style={chart.total}>{value}</Text></View>
    <View style={chart.track} accessible accessibilityLabel={`${label}: ${value}`}>
      <View style={[chart.fill, { width: `${Math.min(100, max > 0 ? value * 100 / max : 0)}%` }]} />
    </View></View>;
}

export function DashboardCrmScreen() {
  const { usuario } = useSession();
  const query = useConsulta<Dashboard>(usuario?.rol === 'admin' ? 'dashboard-crm/' : null);
  const [whatsappSpend, setWhatsappSpend] = useState('0');
  const [emailSpend, setEmailSpend] = useState('0');
  const counts = query.datos?.conteos;
  const n = (key: string) => Number(counts?.[key]) || 0;
  const registros = n('whatsapp_registros') + n('lead_magnet_registros');
  const potenciales = n('whatsapp_potenciales') + n('email_potenciales');
  const citas = n('whatsapp_citas') + n('email_citas');
  const cotizaciones = n('whatsapp_cotizaciones') + n('email_cotizaciones');
  const ventas = n('whatsapp_ventas') + n('email_ventas');
  const gastoW = Math.max(0, Number(whatsappSpend) || 0);
  const gastoE = Math.max(0, Number(emailSpend) || 0);
  const tendencia = query.datos?.tendencia || [];
  const trendMax = Math.max(1, ...tendencia.flatMap(row => [row.whatsapp, row.lead_magnet, row.citas]));
  return <Screen title="Dashboard CRM" subtitle="Marketing y ventas en un solo lugar." refreshing={query.cargando} onRefresh={() => void query.recargar()}>
    {usuario?.rol !== 'admin' ? <Notice message="Esta sección requiere permisos de administrador." tone="info" /> : <>
      {query.error ? <><Notice message={query.error} tone="error" /><Button label="Reintentar" variant="secondary" onPress={() => void query.recargar()} /></> : null}
      {query.cargando && !counts ? <ActivityIndicator color={colors.primary} /> : null}
      {counts ? <><View style={styles.row}><Stat label="Registros" value={String(registros)} /><Stat label="Potenciales" value={String(potenciales)} />
        <Stat label="Citas agendadas" value={String(citas)} /><Stat label="Ventas" value={String(ventas)} /></View>
        <Card><SectionTitle>Embudo comercial</SectionTitle>
          <Funnel label="Registros" value={registros} max={registros} />
          <Funnel label="Clientes potenciales" value={potenciales} max={registros} />
          <Funnel label="Citas agendadas" value={citas} max={registros} />
          <Funnel label="Citas completadas" value={n('whatsapp_completadas') + n('email_completadas')} max={registros} />
          <Funnel label="Cotizaciones enviadas" value={cotizaciones} max={registros} />
          <Funnel label="Ventas confirmadas" value={ventas} max={registros} />
          <Funnel label="Ventas liquidadas" value={n('ventas_liquidadas')} max={registros} />
          <Text style={styles.muted}>Conversión de registros a venta: {percent(ventas, registros)}</Text>
        </Card>
        <Card><SectionTitle>Rendimiento por canal</SectionTitle>
          {[{ label: 'WhatsApp', registros: n('whatsapp_registros'), potenciales: n('whatsapp_potenciales'), citas: n('whatsapp_citas'), ventas: n('whatsapp_ventas') },
            { label: 'Lead Magnet / Email', registros: n('lead_magnet_registros'), potenciales: n('email_potenciales'), citas: n('email_citas'), ventas: n('email_ventas') }].map(channel => <View key={channel.label} style={{ gap: 6 }}>
              <Text style={styles.heading}>{channel.label}</Text><Text style={styles.body}>{channel.registros} registros · {channel.potenciales} potenciales · {channel.citas} citas · {channel.ventas} ventas</Text>
              <Text style={styles.muted}>Conversión: {percent(channel.ventas, channel.registros)}</Text></View>)}
        </Card>
        <Card><SectionTitle>Últimos seis meses</SectionTitle>
          <View style={styles.row}><Text style={[styles.muted, { color: colors.primary }]}>● WhatsApp</Text><Text style={[styles.muted, { color: '#14A59A' }]}>● Lead Magnet</Text><Text style={[styles.muted, { color: '#A78BFA' }]}>● Citas</Text></View>
          {tendencia.map(row => <View key={row.mes} style={{ gap: 5 }}><Text style={styles.body}>{month(row.mes)}</Text>
            {([['WhatsApp', row.whatsapp, colors.primary], ['Lead Magnet', row.lead_magnet, '#14A59A'], ['Citas', row.citas, '#A78BFA']] as const).map(([label, value, color]) => <View key={label} style={chart.trendRow}>
              <View style={chart.trendTrack} accessibilityLabel={`${label}: ${value}`}><View style={[chart.fill, { width: `${value * 100 / trendMax}%`, backgroundColor: color }]} /></View>
              <Text style={styles.muted}>{value}</Text></View>)}
          </View>)}
        </Card>
        <Card><SectionTitle>Costos publicitarios estimados</SectionTitle>
          <Text style={styles.muted}>Introduce la inversión acumulada de cada canal. Estos supuestos solo se usan en esta pantalla y no modifican tus gastos operativos.</Text>
          <Field label="Inversión en WhatsApp (MXN)" value={whatsappSpend} onChangeText={setWhatsappSpend} keyboardType="decimal-pad" maxLength={14} />
          <Field label="Inversión en Lead Magnet (MXN)" value={emailSpend} onChangeText={setEmailSpend} keyboardType="decimal-pad" maxLength={14} />
          <View style={styles.row}><Stat label="Inversión total" value={money(gastoW + gastoE)} /><Stat label="Costo por registro" value={cost(gastoW + gastoE, registros)} /><Stat label="Costo por venta" value={cost(gastoW + gastoE, ventas)} /></View>
          <Text style={styles.body}>WhatsApp: {cost(gastoW, n('whatsapp_registros'))} por registro · {cost(gastoW, n('whatsapp_ventas'))} por venta</Text>
          <Text style={styles.body}>Lead Magnet: {cost(gastoE, n('lead_magnet_registros'))} por registro · {cost(gastoE, n('email_ventas'))} por venta</Text>
        </Card>
        <Card><SectionTitle>Seguimiento de Email Marketing</SectionTitle><Text style={styles.body}>{n('lead_magnet_consentimiento')} leads con consentimiento · {n('lead_magnet_tips')} consejos enviados · {n('lead_magnet_feedback')} feedbacks enviados</Text></Card>
        <Text style={styles.muted}>{query.datos?.alcance}</Text>
      </> : null}
    </>}
  </Screen>;
}

const chart = StyleSheet.create({
  funnel: { gap: 6 }, legend: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  total: { color: colors.ink, fontWeight: '700' }, track: { height: 9, backgroundColor: '#EBF0F8', borderRadius: 6, overflow: 'hidden' },
  fill: { height: '100%', backgroundColor: colors.primary, borderRadius: 6 },
  trendRow: { flexDirection: 'row', gap: 10, alignItems: 'center' }, trendTrack: { flex: 1, backgroundColor: '#EBF0F8', height: 7, borderRadius: 6, overflow: 'hidden' },
});
