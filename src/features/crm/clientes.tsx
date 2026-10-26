import { useRef, useState } from 'react';
import { router, type Href } from 'expo-router';
import { ActivityIndicator, FlatList, StyleSheet, Text, View } from 'react-native';
import { Button, Card, Chip, Empty, Field, Notice, Pagination, Row, Screen, SectionTitle, Stat, Toggle, colors, sharedStyles } from '@/components/meg';
import { useConsulta } from '@/hooks/use-consulta';
import { peticionSistema } from '@/services/api';

type Cliente = {
  id: string; nombre: string; correo: string; telefono: string; comentarios: string;
  hubo_venta: boolean; monto_venta: string | null; descripcion_servicio: string;
};
type Respuesta = { clientes: Cliente[]; total: number; pagina: number; paginas: number };
type Borrador = Omit<Cliente, 'id' | 'monto_venta'> & { monto_venta: string };
const vacio = (): Borrador => ({ nombre: '', correo: '', telefono: '', comentarios: '', hubo_venta: false, monto_venta: '', descripcion_servicio: '' });
const dinero = (value: string | number | null) => new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(Number(value || 0));
const errorTexto = (error: unknown) => error instanceof Error ? error.message : 'No se pudieron guardar los cambios.';

function FormularioCliente({ cliente, onSave, onCancel }: { cliente: Cliente | null; onSave: () => Promise<void>; onCancel: () => void }) {
  const [datos, setDatos] = useState<Borrador>(() => cliente ? {
    nombre: cliente.nombre, correo: cliente.correo, telefono: cliente.telefono, comentarios: cliente.comentarios,
    hubo_venta: cliente.hubo_venta, monto_venta: cliente.monto_venta || '', descripcion_servicio: cliente.descripcion_servicio,
  } : vacio());
  const [guardando, setGuardando] = useState(false);
  const bloqueo = useRef(false);
  const [error, setError] = useState('');
  const cambiar = <K extends keyof Borrador>(campo: K, valor: Borrador[K]) => setDatos(prev => ({ ...prev, [campo]: valor }));
  async function guardar() {
    if (bloqueo.current) return;
    if (!datos.nombre.trim() || !datos.telefono.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(datos.correo.trim())) {
      setError('Completa nombre, correo válido y teléfono.'); return;
    }
    const monto = datos.monto_venta.trim().replace(',', '.');
    if (datos.hubo_venta && (!/^\d+(\.\d{1,2})?$/.test(monto) || Number(monto) <= 0 || Number(monto) > 9999999999.99 || !datos.descripcion_servicio.trim())) {
      setError('Para registrar una venta, indica un monto mayor que cero y describe el servicio contratado.'); return;
    }
    bloqueo.current = true; setGuardando(true); setError('');
    try {
      await peticionSistema(cliente ? `clientes/${cliente.id}/` : 'clientes/', {
        metodo: cliente ? 'PATCH' : 'POST', datos: {
          ...datos, nombre: datos.nombre.trim(), correo: datos.correo.trim().toLowerCase(), telefono: datos.telefono.trim(),
          monto_venta: datos.hubo_venta ? monto : null, descripcion_servicio: datos.hubo_venta ? datos.descripcion_servicio.trim() : '',
        },
      });
      await onSave();
    } catch (err) { setError(errorTexto(err)); }
    finally { bloqueo.current = false; setGuardando(false); }
  }
  return <Card>
    <SectionTitle>{cliente ? 'Editar registro' : 'Registrar prospecto'}</SectionTitle>
    <Field label="Nombre del cliente *" value={datos.nombre} onChangeText={v => cambiar('nombre', v)} maxLength={150} editable={!guardando} autoCapitalize="words" />
    <Field label="Correo *" value={datos.correo} onChangeText={v => cambiar('correo', v)} maxLength={254} keyboardType="email-address" autoCapitalize="none" autoCorrect={false} editable={!guardando} />
    <Field label="Teléfono *" value={datos.telefono} onChangeText={v => cambiar('telefono', v)} maxLength={25} keyboardType="phone-pad" editable={!guardando} />
    <Field label="Comentarios" value={datos.comentarios} onChangeText={v => cambiar('comentarios', v)} maxLength={2000} multiline editable={!guardando} placeholder="Necesidades, acuerdos o siguiente paso" />
    <Toggle label="Hubo venta" value={datos.hubo_venta} onValueChange={v => cambiar('hubo_venta', v)} disabled={guardando} />
    {datos.hubo_venta && <>
      <Field label="Monto de la venta (MXN) *" value={datos.monto_venta} onChangeText={v => cambiar('monto_venta', v)} keyboardType="decimal-pad" maxLength={13} editable={!guardando} placeholder="0.00" />
      <Field label="Descripción del servicio *" value={datos.descripcion_servicio} onChangeText={v => cambiar('descripcion_servicio', v)} maxLength={2000} multiline editable={!guardando} placeholder="Ej. Aplicación de inventario para Android y iOS" />
      <Text style={sharedStyles.caption}>La venta aparecerá en Proyectos. Los cobros se registran en Finanzas.</Text>
    </>}
    <Notice message={error} />
    <Button label="Guardar cambios" icon="checkmark-outline" onPress={() => void guardar()} loading={guardando} />
    <Button label="Cancelar" variant="secondary" onPress={onCancel} disabled={guardando} />
  </Card>;
}

export function ClientesScreen() {
  const [texto, setTexto] = useState('');
  const [buscar, setBuscar] = useState('');
  const [venta, setVenta] = useState('todos');
  const [pagina, setPagina] = useState(1);
  const [formulario, setFormulario] = useState<{ cliente: Cliente | null } | null>(null);
  const [aviso, setAviso] = useState('');
  const list = useRef<FlatList<Cliente>>(null);
  const params = new URLSearchParams({ buscar, venta, pagina: String(pagina) });
  const { datos, error, cargando, recargar } = useConsulta<Respuesta>(`clientes/?${params}`);
  function abrir(cliente: Cliente | null) { setFormulario({ cliente }); setAviso(''); list.current?.scrollToOffset({ offset: 0, animated: true }); }
  const filtrar = () => { setPagina(1); setBuscar(texto.trim()); setFormulario(null); };
  return <Screen title="Clientes y prospectos" subtitle="De la primera conversación al próximo proyecto." scroll={false}>
    <FlatList ref={list} style={{ flex: 1 }} data={datos?.clientes || []} keyExtractor={item => item.id}
      keyboardShouldPersistTaps="handled" refreshing={cargando} onRefresh={formulario ? undefined : () => void recargar()} initialNumToRender={6} windowSize={5}
      contentContainerStyle={{ gap: 14, paddingBottom: 24 }}
      ListHeaderComponent={<View style={{ gap: 14 }}>
        <Card><Field label="Buscar por nombre, correo o teléfono" value={texto} onChangeText={setTexto} placeholder="Encuentra un cliente" maxLength={100} returnKeyType="search" onSubmitEditing={filtrar} />
          <Button label="Buscar" variant="secondary" icon="search-outline" onPress={filtrar} />
          <Text style={sharedStyles.caption}>Hubo venta</Text><Row>{[['todos', 'Todos'], ['si', 'Sí'], ['no', 'No']].map(([value, label]) => <Chip key={value} label={label} selected={venta === value} onPress={() => { setVenta(value); setPagina(1); setFormulario(null); }} />)}</Row>
        </Card>
        {!formulario && <Button label="Registrar prospecto" icon="person-add-outline" onPress={() => abrir(null)} />}
        {formulario && <FormularioCliente key={formulario.cliente?.id || 'nuevo'} cliente={formulario.cliente} onCancel={() => setFormulario(null)} onSave={async () => { setFormulario(null); setAviso('Registro guardado correctamente.'); await recargar(); }} />}
        <Notice message={aviso} tone="success" /><Notice message={error} />
        {Boolean(error) && <Button label="Reintentar" variant="secondary" onPress={() => void recargar()} />}
        {datos && <SectionTitle>{datos.total} {datos.total === 1 ? 'registro' : 'registros'}</SectionTitle>}
      </View>}
      ListEmptyComponent={cargando ? <ActivityIndicator color={colors.primary} /> : error ? undefined : <Empty message="No hay registros para estos filtros. Registra tu primer prospecto." />}
      renderItem={({ item }) => <Card>
        <Row><Chip label={item.hubo_venta ? 'Venta registrada' : 'Prospecto'} selected={item.hubo_venta} /></Row>
        <Text style={sharedStyles.title}>{item.nombre}</Text>
        <Text selectable style={sharedStyles.body}>{item.correo}</Text><Text selectable style={sharedStyles.caption}>{item.telefono}</Text>
        {Boolean(item.comentarios) && <Text style={sharedStyles.body}>{item.comentarios}</Text>}
        {item.hubo_venta && <><Text style={styles.amount}>{dinero(item.monto_venta)}</Text><Text style={sharedStyles.body}>{item.descripcion_servicio}</Text></>}
        <Button label={`Editar a ${item.nombre}`} variant="secondary" onPress={() => abrir(item)} />
      </Card>}
      ListFooterComponent={<Pagination pagina={pagina} paginas={datos?.paginas || 0} onChange={value => { setPagina(value); list.current?.scrollToOffset({ offset: 0, animated: true }); }} />} />
  </Screen>;
}

type Dashboard = {
  total_clientes: number; total_ventas: number; prospectos: number; monto_ventas: string; conversion_pct: string;
  ventas_recientes: Cliente[]; tendencia: { mes: string; ventas: number; monto: string }[];
};
export function DashboardComercialScreen() {
  const { datos, cargando, error, recargar } = useConsulta<Dashboard>('dashboard-crm/');
  const maximo = Math.max(1, ...(datos?.tendencia || []).map(mes => Number(mes.monto)));
  return <Screen title="Dashboard CRM" subtitle="Tus oportunidades y ventas, en un solo lugar." refreshing={cargando} onRefresh={recargar}>
    <Notice message={error} />{Boolean(error) && <Button label="Reintentar" variant="secondary" onPress={() => void recargar()} />}
    {cargando && !datos && <ActivityIndicator color={colors.primary} />}
    {datos && <>
      <Row><Stat label="Contactos registrados" value={datos.total_clientes} /><Stat label="Prospectos" value={datos.prospectos} /></Row>
      <Row><Stat label="Ventas cerradas" value={datos.total_ventas} /><Stat label="Conversión" value={`${Number(datos.conversion_pct).toFixed(1)}%`} /></Row>
      <Card><Text style={sharedStyles.caption}>VALOR TOTAL DE VENTAS · MXN</Text><Text style={styles.amount}>{dinero(datos.monto_ventas)}</Text><Text style={sharedStyles.caption}>Importe contratado. Los pagos recibidos se consultan en Finanzas.</Text></Card>
      <Card><SectionTitle>Ventas por mes</SectionTitle>{datos.tendencia.map(mes => <View key={mes.mes} style={{ gap: 8 }}><Row><Text style={sharedStyles.body}>{mes.mes}</Text><Text style={sharedStyles.caption}>{mes.ventas} ventas · {dinero(mes.monto)}</Text></Row><View style={styles.track}><View style={[styles.bar, { width: `${Math.max(0, Number(mes.monto) / maximo * 100)}%` }]} /></View></View>)}</Card>
      <SectionTitle>Ventas recientes</SectionTitle>
      {datos.ventas_recientes.length ? datos.ventas_recientes.map(cliente => <Card key={cliente.id}><Text style={sharedStyles.title}>{cliente.nombre}</Text><Text style={sharedStyles.body}>{cliente.descripcion_servicio}</Text><Text style={styles.amount}>{dinero(cliente.monto_venta)}</Text></Card>) : <Empty message="Las ventas aparecerán aquí cuando registres la primera." />}
    </>}
    <Button label="Ver clientes y prospectos" icon="people-outline" onPress={() => router.push('/crm/clientes' as Href)} />
  </Screen>;
}

const styles = StyleSheet.create({
  amount: { color: colors.primary, fontSize: 27, fontWeight: '800', fontVariant: ['tabular-nums'] },
  track: { height: 8, backgroundColor: '#EAF0F8', borderRadius: 4, overflow: 'hidden', marginBottom: 10 },
  bar: { height: '100%', backgroundColor: colors.primary, borderRadius: 4 },
});
