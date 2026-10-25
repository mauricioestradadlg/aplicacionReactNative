import Ionicons from '@expo/vector-icons/Ionicons';
import { LinearGradient } from 'expo-linear-gradient';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button, Card, Field, Notice, colors } from '@/components/meg';
import { useSession } from '@/context/session';
import { API_URL, guardarToken, peticionSistema, rutaAuth } from '@/services/api';

export default function LoginScreen() {
  const { comprobarSesion, error: sessionError } = useSession();
  const [usuario, setUsuario] = useState('');
  const [contrasena, setContrasena] = useState('');
  const [visible, setVisible] = useState(false);
  const [verificacion, setVerificacion] = useState<{ id: string; correo: string } | null>(null);
  const [codigo, setCodigo] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function enviar() {
    if (loading) return;
    setError('');
    if (!verificacion && (!usuario.trim() || !contrasena)) { setError('Ingresa tu usuario y contraseña.'); return; }
    if (verificacion && !/^\d{6}$/.test(codigo)) { setError('Ingresa los seis dígitos del código.'); return; }
    setLoading(true);
    try {
      if (!verificacion) {
        const r = await peticionSistema<{ verificacion_id: string; correo_oculto: string }>(rutaAuth('login'), { metodo: 'POST', datos: { usuario: usuario.trim(), contrasena } });
        setContrasena('');
        setVerificacion({ id: r.verificacion_id, correo: r.correo_oculto });
      } else {
        const r = await peticionSistema<{ token?: string }>(rutaAuth('verificar'), { metodo: 'POST', datos: { verificacion_id: verificacion.id, codigo } });
        if (Platform.OS !== 'web') {
          if (!r.token) throw new Error('El backend no devolvió una sesión móvil. Actualiza el backend con la versión incluida en este proyecto.');
          try { await guardarToken(r.token); }
          catch { throw new Error('No se pudo guardar la sesión de forma segura. Intenta de nuevo.'); }
        }
        setCodigo('');
        setVerificacion(null);
        await comprobarSesion();
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'No fue posible iniciar sesión.'); }
    finally { setLoading(false); }
  }

  return <LinearGradient colors={['#070F21', '#102D54', '#0A1830']} style={styles.flex}>
    <SafeAreaView style={styles.flex}><KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>
        <View style={styles.brand}><View style={styles.logo}><Text style={styles.logoText}>MEG<Text style={styles.logoDot}>.</Text></Text></View><View><Text style={styles.brandTitle}>PROYECTOS MEG</Text><Text style={styles.brandSubtitle}>Soluciones que hacen crecer negocios</Text></View></View>
        <View style={styles.hero}><View style={styles.label}><View style={styles.dot} /><Text style={styles.labelText}>TU ESPACIO DE TRABAJO</Text></View><Text style={styles.heroTitle}>Todo tu negocio.{ '\n' }En tus manos.</Text><Text style={styles.heroDescription}>Clientes, proyectos y finanzas conectados en un solo lugar.</Text></View>
        <Card style={styles.loginCard}>
          <View style={styles.cardIcon}><Ionicons name={verificacion ? 'shield-checkmark-outline' : 'lock-closed-outline'} color={colors.primary} size={25} /></View>
          <Text style={styles.cardTitle}>{verificacion ? 'Verifica tu identidad' : 'Bienvenido de nuevo'}</Text>
          <Text style={styles.description}>{verificacion ? `Enviamos un código a ${verificacion.correo}. Ingresa los seis dígitos antes de 10 minutos.` : 'Ingresa con tu cuenta del sistema interno.'}</Text>
          {!API_URL && <Notice tone="info" message="Configura la dirección de tu servidor local en .env. Las instrucciones están en README.md." />}
          {verificacion ? <Field label="Código de verificación" placeholder="000000" value={codigo} onChangeText={value => setCodigo(value.replace(/\D/g, '').slice(0, 6))} keyboardType="number-pad" autoComplete="one-time-code" textContentType="oneTimeCode" maxLength={6} autoFocus style={styles.code} /> : <>
            <Field label="Usuario" placeholder="Tu nombre de usuario" value={usuario} onChangeText={setUsuario} autoCapitalize="none" autoCorrect={false} autoComplete="username" textContentType="username" returnKeyType="next" maxLength={80} editable={!loading} />
            <Field label="Contraseña" placeholder="Ingresa tu contraseña" value={contrasena} onChangeText={setContrasena} secureTextEntry={!visible} autoCapitalize="none" autoComplete="current-password" textContentType="password" onSubmitEditing={() => void enviar()} returnKeyType="go" editable={!loading} />
            <Pressable accessibilityRole="button" accessibilityLabel={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'} onPress={() => setVisible(!visible)} style={styles.showPassword}><Ionicons name={visible ? 'eye-off-outline' : 'eye-outline'} color={colors.muted} size={17} /><Text style={styles.showText}>{visible ? 'Ocultar contraseña' : 'Mostrar contraseña'}</Text></Pressable>
          </>}
          <Notice message={error || sessionError} />
          {Boolean(sessionError) && <Button label="Reintentar conexión de la sesión" variant="secondary" loading={loading} onPress={() => void comprobarSesion()} />}
          <Button label={verificacion ? 'Verificar y entrar' : 'Continuar'} icon="arrow-forward" loading={loading} disabled={!API_URL || (Boolean(verificacion) && codigo.length !== 6)} onPress={() => void enviar()} />
          {verificacion && <Button variant="secondary" label="Volver al inicio de sesión" disabled={loading} onPress={() => { setVerificacion(null); setCodigo(''); setError(''); }} />}
          <View style={styles.security}><Ionicons name="shield-checkmark-outline" color={colors.muted} size={15} /><Text style={styles.securityText}>Acceso exclusivo para personal autorizado</Text></View>
        </Card>
        <Text style={styles.footer}>PROYECTOS MEG  ·  SISTEMA INTERNO</Text>
      </ScrollView>
    </KeyboardAvoidingView></SafeAreaView>
  </LinearGradient>;
}

const styles = StyleSheet.create({
  flex: { flex: 1 }, content: { flexGrow: 1, padding: 26, gap: 32, justifyContent: 'center', width: '100%', maxWidth: 510, alignSelf: 'center' },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 12 }, logo: { width: 57, height: 57, backgroundColor: '#176CF2', borderRadius: 17, alignItems: 'center', justifyContent: 'center' }, logoText: { color: '#FFF', fontSize: 20, fontWeight: '900', letterSpacing: -1 }, logoDot: { color: '#89BBFF' }, brandTitle: { color: '#FFF', fontSize: 13, fontWeight: '800', letterSpacing: 1.7 }, brandSubtitle: { color: '#94ACCB', fontSize: 10, marginTop: 6 },
  hero: { gap: 15 }, label: { flexDirection: 'row', alignItems: 'center', gap: 7 }, dot: { height: 6, width: 6, borderRadius: 3, backgroundColor: '#67ADFF' }, labelText: { fontSize: 10, fontWeight: '700', letterSpacing: 2.2, color: '#8DBDFF' }, heroTitle: { fontSize: 39, lineHeight: 45, fontWeight: '800', color: '#FFF', letterSpacing: -1.5 }, heroDescription: { fontSize: 14, lineHeight: 23, color: '#A0B6D4', maxWidth: 320 },
  loginCard: { width: '100%', padding: 25, borderRadius: 23, gap: 15 }, cardIcon: { width: 48, height: 48, borderRadius: 15, backgroundColor: '#EAF2FF', justifyContent: 'center', alignItems: 'center' }, cardTitle: { fontSize: 23, color: colors.ink, fontWeight: '800', letterSpacing: -0.7 }, description: { color: colors.muted, fontSize: 13, lineHeight: 21, marginTop: -6, marginBottom: 4 },
  showPassword: { minHeight: 32, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }, showText: { color: colors.muted, fontSize: 12 }, security: { flexDirection: 'row', gap: 6, alignItems: 'center', justifyContent: 'center', paddingTop: 5 }, securityText: { fontSize: 10, color: colors.muted, flexShrink: 1 }, footer: { color: '#7891B3', textAlign: 'center', fontSize: 10, letterSpacing: 2 }, code: { textAlign: 'center', fontSize: 27, letterSpacing: 9 },
});
