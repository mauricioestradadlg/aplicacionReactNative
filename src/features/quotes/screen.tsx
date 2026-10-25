import { useMemo, useState } from 'react';
import { Platform, Text } from 'react-native';
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';
import { Button, Card, Chip, Field, Notice, Pagination, Row, Screen, SectionTitle, Stat, Toggle, sharedStyles } from '@/components/meg';
import { useSession } from '@/context/session';
import { useConsulta } from '@/hooks/use-consulta';
import { calcularCotizacion, DOMINIOS, money, nuevaCotizacion, SERVICIOS, type Cotizacion } from './calculos';
import { documentoCotizacion } from './documento';

type Cliente = { id: string; fuente: string; nombre: string; negocio: string; telefono: string; correo?: string; servicio_recomendado: string };
export default function CotizacionScreen() {
  const { usuario } = useSession();
  const admin = usuario?.rol === 'admin';
  const [form, setForm] = useState(nuevaCotizacion);
  const [importando, setImportando] = useState(false);
  const [pagina, setPagina] = useState(1);
  const { datos, error: errorCrm, cargando } = useConsulta<{ prospectos: Cliente[]; paginas: number }>(admin && importando ? `cierre-ventas/?pagina=${pagina}` : null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const calc = useMemo(() => calcularCotizacion(form), [form]);
  function cambiar<K extends keyof Cotizacion>(key: K, value: Cotizacion[K]) { setForm(previous => ({ ...previous, [key]: value })); }
  async function exportar() {
    if (loading) return;
    setError(''); setSuccess('');
    if (!form.nombre.trim() || !form.negocio.trim() || !form.folio.trim()) { setError('Completa nombre del cliente, negocio y folio.'); return; }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(form.fecha) || Number.isNaN(Date.parse(`${form.fecha}T12:00:00`)) || new Date(`${form.fecha}T12:00:00`).toISOString().slice(0, 10) !== form.fecha) { setError('Ingresa una fecha válida con formato AAAA-MM-DD.'); return; }
    if (form.dominio && !(Number(form.costoDominio) > 0)) { setError('Confirma el costo del dominio antes de exportar.'); return; }
    if (![Number(form.cantidadFunciones), Number(form.costoDominio)].every(Number.isFinite)) { setError('Revisa los campos numéricos de la propuesta.'); return; }
    setLoading(true);
    try {
      const html = documentoCotizacion(form);
      if (Platform.OS === 'web') await Print.printAsync({ html });
      else {
        const file = await Print.printToFileAsync({ html });
        if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(file.uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf', dialogTitle: `Cotización ${form.folio}` });
        else await Print.printAsync({ uri: file.uri });
      }
      setSuccess('Documento preparado. Puedes guardarlo o compartirlo desde las opciones del sistema.');
    } catch { setError('No se pudo generar o abrir el documento. Intenta de nuevo.'); }
    finally { setLoading(false); }
  }
  return <Screen title="Crear cotización" subtitle="La misma propuesta comercial, lista para compartir desde tu celular.">
    {!admin ? <Notice message="Solo un administrador puede generar cotizaciones." /> : <>
      <Card><SectionTitle>1. Cliente y propuesta</SectionTitle><Button label={importando ? 'Cerrar selector de CRM' : 'Importar prospecto del CRM'} variant="secondary" onPress={() => setImportando(!importando)} />
        {importando && <><Notice message={errorCrm} />{cargando ? <Text style={sharedStyles.caption}>Consultando prospectos…</Text> : datos?.prospectos.map(c => <Button key={`${c.fuente}:${c.id}`} label={`${c.nombre || c.telefono} · ${c.negocio || c.fuente}`} variant="secondary" onPress={() => { setForm(p => ({ ...p, nombre: c.nombre || '', negocio: c.negocio || '', telefono: c.telefono || '', correo: c.correo || '', servicio: c.servicio_recomendado === 'sitio-web' ? 'sitio-web' : 'landing-page' })); setImportando(false); }} />)}{datos && <Pagination pagina={pagina} paginas={datos.paginas} onChange={setPagina} />}</>}
        <Field label="Nombre del cliente *" value={form.nombre} onChangeText={v => cambiar('nombre', v)} maxLength={100} />
        <Field label="Negocio *" value={form.negocio} onChangeText={v => cambiar('negocio', v)} maxLength={120} />
        <Field label="Teléfono / WhatsApp" value={form.telefono} onChangeText={v => cambiar('telefono', v)} keyboardType="phone-pad" maxLength={30} />
        <Field label="Correo" value={form.correo} onChangeText={v => cambiar('correo', v)} autoCapitalize="none" keyboardType="email-address" maxLength={160} />
        <Field label="Folio *" value={form.folio} onChangeText={v => cambiar('folio', v)} maxLength={50} />
        <Field label="Fecha (AAAA-MM-DD)" value={form.fecha} onChangeText={v => cambiar('fecha', v)} maxLength={10} />
        <Field label="Objetivo del proyecto" value={form.objetivo} onChangeText={v => cambiar('objetivo', v)} multiline maxLength={650} />
      </Card>
      <Card><SectionTitle>2. Servicio y extras</SectionTitle><Row>{(Object.keys(SERVICIOS) as (keyof typeof SERVICIOS)[]).map(key => <Chip key={key} label={`${SERVICIOS[key].nombre} · ${money(key === 'landing-page' ? 3500 : 6000)}`} selected={form.servicio === key} onPress={() => cambiar('servicio', key)} />)}</Row>
        <Text style={sharedStyles.caption}>{SERVICIOS[form.servicio].descripcion}</Text>
        <Toggle label="Formulario de contacto · $1,000" value={form.formulario} onValueChange={v => cambiar('formulario', v)} />
        <Toggle label="Panel administrativo · $3,000" value={form.panel} onValueChange={v => cambiar('panel', v)} />
        <Field label="Funcionalidades adicionales (0–20) · $2,000 c/u" value={String(form.cantidadFunciones)} keyboardType="number-pad" onChangeText={v => cambiar('cantidadFunciones', v.replace(/\D/g, '').slice(0, 2))} maxLength={2} />
        <Field label="Detalle de las funcionalidades" value={form.funcionalidadesDetalle} onChangeText={v => cambiar('funcionalidadesDetalle', v)} multiline maxLength={1000} />
        <Text style={sharedStyles.body}>Descuento sobre el desarrollo</Text><Row>{[['ninguno', 'Sin descuento'], ['plantilla', 'Plantilla · 10 %'], ['diseno', 'Diseño previo · 20 %']].map(([key, label]) => <Chip key={key} label={label} selected={form.descuento === key} onPress={() => cambiar('descuento', key)} />)}</Row>
      </Card>
      <Card><SectionTitle>3. Dominio y mantenimiento</SectionTitle><Row>{['', ...Object.keys(DOMINIOS)].map(extension => <Chip key={extension} label={extension || 'Sin dominio'} selected={form.dominio === extension} onPress={() => setForm(p => ({ ...p, dominio: extension, costoDominio: extension ? DOMINIOS[extension as keyof typeof DOMINIOS] : '' }))} />)}</Row>
        {Boolean(form.dominio) && <><Field label="Costo confirmado del dominio · MXN" value={String(form.costoDominio)} keyboardType="decimal-pad" onChangeText={v => cambiar('costoDominio', v.replace(',', '.'))} maxLength={12} /><Text style={sharedStyles.caption}>Precio de referencia editable; confirma disponibilidad y costo. Gestión del dominio: $300 adicionales.</Text></>}
        <Toggle label="Mantenimiento mensual opcional · 10 % del desarrollo" value={form.mantenimiento} onValueChange={v => cambiar('mantenimiento', v)} />
        <Toggle label="Beneficio por referido · 30 días adicionales" value={form.referido} onValueChange={v => cambiar('referido', v)} />
        <Field label="Observaciones" value={form.notas} onChangeText={v => cambiar('notas', v)} multiline maxLength={2000} />
      </Card>
      <SectionTitle>Tu propuesta</SectionTitle><Row><Stat label="Inversión inicial · IVA incluido" value={money(calc.totalInicial)} /><Stat label="Primer pago" value={money(calc.primerPago)} /></Row>
      <Card>{calc.conceptos.map(c => <Text key={c.descripcion} style={sharedStyles.body}>{c.cantidad} × {c.descripcion}: {money(c.cantidad * c.unitario)}</Text>)}<Text style={sharedStyles.body}>Descuento: {money(calc.descuentoImporte)}</Text><Text style={sharedStyles.body}>Dominio y gestión: {money(calc.totalDominio)}</Text><Text style={sharedStyles.body}>Segundo pago: {money(calc.saldoDesarrollo)}</Text><Text style={sharedStyles.caption}>Base sin IVA: {money(calc.baseSinIVA)} · IVA incluido: {money(calc.ivaIncluido)}</Text>{form.mantenimiento && <Text style={sharedStyles.body}>Mantenimiento mensual posterior: {money(calc.mensualidad)}</Text>}<Text style={sharedStyles.caption}>Vigencia: 30 días. La cotización se genera como documento, igual que en la web.</Text></Card>
      <Notice message={error} /><Notice message={success} tone="success" /><Button label={Platform.OS === 'web' ? 'Imprimir o guardar PDF' : 'Generar y compartir PDF'} icon="share-outline" loading={loading} onPress={() => void exportar()} />
    </>}
  </Screen>;
}
