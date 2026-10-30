import Ionicons from '@expo/vector-icons/Ionicons';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { router, type Href } from 'expo-router';
import { useRef, useState, type ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button, Card, Field, Notice, colors } from '@/components/meg';
import { useSession } from '@/context/session';
import { API_URL, guardarToken, peticionSistema, rutaAuth } from '@/services/api';
import { errorTexto } from './common';

function AuthFrame({ children, registro = false }: { children: ReactNode; registro?: boolean }) {
  return <LinearGradient colors={['#070F21', '#102D54', '#0A1830']} style={styles.flex}>
    <SafeAreaView edges={registro ? ['left', 'right', 'bottom'] : ['top', 'left', 'right', 'bottom']} style={styles.flex}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>
          <View style={styles.brand}>
            <Image source={require('@/assets/images/logo-meg.png')} style={styles.logo} contentFit="contain" accessible accessibilityLabel="Logo de Proyectos MEG" />
            <View style={styles.brandCopy}><Text style={styles.brandTitle}>PROYECTOS MEG</Text><Text style={styles.brandSubtitle}>Gestión para empresas de software</Text></View>
          </View>
          <Card style={styles.loginCard}>{children}</Card>
          <Text style={styles.footer}>CLIENTES · PROYECTOS · FINANZAS</Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  </LinearGradient>;
}

function PasswordVisibility({ visible, onPress }: { visible: boolean; onPress: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'} onPress={onPress} style={styles.showPassword}><Ionicons name={visible ? 'eye-off-outline' : 'eye-outline'} color={colors.muted} size={18} /><Text style={styles.showText}>{visible ? 'Ocultar contraseña' : 'Mostrar contraseña'}</Text></Pressable>;
}

export function LoginScreen() {
  const { comprobarSesion, error: sessionError } = useSession();
  const [usuario, setUsuario] = useState('');
  const [contrasena, setContrasena] = useState('');
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const bloqueo = useRef(false);
  async function enviar() {
    if (bloqueo.current) return;
    setError('');
    if (!usuario.trim() || !contrasena) { setError('Ingresa tu usuario, correo o teléfono y tu contraseña.'); return; }
    bloqueo.current = true; setLoading(true);
    try {
      const result = await peticionSistema<{ token?: string }>(rutaAuth('login'), { metodo: 'POST', datos: { usuario: usuario.trim(), contrasena } });
      if (Platform.OS !== 'web') {
        if (!result.token) throw new Error('No se pudo preparar tu sesión móvil. Intenta de nuevo.');
        await guardarToken(result.token);
      }
      setContrasena('');
      await comprobarSesion();
    } catch (err) { setError(errorTexto(err)); }
    finally { bloqueo.current = false; setLoading(false); }
  }
  return <AuthFrame>
    <View style={styles.cardIcon}><Ionicons name="lock-closed-outline" color={colors.primary} size={25} /></View>
    <Text accessibilityRole="header" style={styles.cardTitle}>Bienvenido de nuevo</Text>
    <Text style={styles.description}>Entra a tu espacio de trabajo.</Text>
    {!API_URL && <Notice tone="info" message="La conexión con el servidor aún no está configurada." />}
    <Field label="Usuario, correo o teléfono" placeholder="¿Cómo te registraste?" value={usuario} onChangeText={setUsuario} autoCapitalize="none" autoCorrect={false} autoComplete="username" textContentType="username" returnKeyType="next" maxLength={254} editable={!loading} />
    <Field label="Contraseña" placeholder="Ingresa tu contraseña" value={contrasena} onChangeText={setContrasena} secureTextEntry={!visible} autoCapitalize="none" autoComplete="current-password" textContentType="password" onSubmitEditing={() => void enviar()} returnKeyType="go" maxLength={256} editable={!loading} />
    <PasswordVisibility visible={visible} onPress={() => setVisible(!visible)} />
    <Notice message={error || sessionError} />
    {Boolean(sessionError) && <Button label="Reintentar conexión" variant="secondary" loading={loading} onPress={() => void comprobarSesion()} />}
    <Button label="Entrar" icon="arrow-forward" loading={loading} disabled={!API_URL} onPress={() => void enviar()} />
    <Text style={styles.divider}>¿Es tu primera vez aquí?</Text>
    <Button label="Crear una cuenta" variant="secondary" disabled={loading} onPress={() => router.push('/registro' as Href)} />
  </AuthFrame>;
}

export function RegistroScreen() {
  const { comprobarSesion, error: sessionError } = useSession();
  const [form, setForm] = useState({ nombre_completo: '', correo: '', telefono: '', usuario: '', contrasena: '' });
  const [confirmacion, setConfirmacion] = useState('');
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const bloqueo = useRef(false);
  const cambiar = (campo: keyof typeof form, valor: string) => setForm(prev => ({ ...prev, [campo]: valor }));
  async function crear() {
    if (bloqueo.current) return;
    setError('');
    if (!form.nombre_completo.trim() || !form.correo.trim() || !form.telefono.trim() || !form.usuario.trim()) { setError('Completa todos los datos de tu cuenta.'); return; }
    if (!/^[a-z][a-z0-9_.-]{2,79}$/.test(form.usuario.trim().toLowerCase())) { setError('El usuario debe comenzar con una letra y tener entre 3 y 80 letras, números, puntos, guiones o guiones bajos.'); return; }
    if (form.contrasena.length < 10) { setError('Usa una contraseña de al menos 10 caracteres.'); return; }
    if (form.contrasena !== confirmacion) { setError('Las contraseñas no coinciden.'); return; }
    bloqueo.current = true; setLoading(true);
    try {
      const result = await peticionSistema<{ token?: string }>(rutaAuth('registro'), { metodo: 'POST', datos: { ...form, nombre_completo: form.nombre_completo.trim(), correo: form.correo.trim().toLowerCase(), usuario: form.usuario.trim().toLowerCase(), telefono: form.telefono.trim() } });
      if (Platform.OS !== 'web') {
        if (!result.token) throw new Error('No se pudo preparar tu sesión móvil. Inicia sesión con tu cuenta.');
        await guardarToken(result.token);
      }
      setForm(prev => ({ ...prev, contrasena: '' })); setConfirmacion('');
      await comprobarSesion();
    } catch (err) { setError(errorTexto(err)); }
    finally { bloqueo.current = false; setLoading(false); }
  }
  return <AuthFrame registro>
    <View style={styles.cardIcon}><Ionicons name="person-add-outline" color={colors.primary} size={25} /></View>
    <Text accessibilityRole="header" style={styles.cardTitle}>Crea tu cuenta</Text>
    <Text style={styles.description}>Después podrás crear una organización o solicitar acceso a tu equipo.</Text>
    <Field label="Nombre completo" value={form.nombre_completo} onChangeText={v => cambiar('nombre_completo', v)} autoComplete="name" textContentType="name" maxLength={150} editable={!loading} />
    <Field label="Correo electrónico" placeholder="nombre@empresa.com" value={form.correo} onChangeText={v => cambiar('correo', v)} keyboardType="email-address" autoCapitalize="none" autoCorrect={false} autoComplete="email" textContentType="emailAddress" maxLength={254} editable={!loading} />
    <Field label="Teléfono" placeholder="Incluye la lada" value={form.telefono} onChangeText={v => cambiar('telefono', v)} keyboardType="phone-pad" autoComplete="tel" textContentType="telephoneNumber" maxLength={25} editable={!loading} />
    <Field label="Nombre de usuario" placeholder="Tu nombre para iniciar sesión" value={form.usuario} onChangeText={v => cambiar('usuario', v)} autoCapitalize="none" autoCorrect={false} autoComplete="username-new" textContentType="username" maxLength={80} editable={!loading} />
    <Field label="Contraseña" placeholder="Al menos 10 caracteres" value={form.contrasena} onChangeText={v => cambiar('contrasena', v)} secureTextEntry={!visible} autoCapitalize="none" autoComplete="new-password" textContentType="newPassword" maxLength={256} editable={!loading} />
    <Field label="Confirmar contraseña" value={confirmacion} onChangeText={setConfirmacion} secureTextEntry={!visible} autoCapitalize="none" autoComplete="new-password" textContentType="newPassword" maxLength={256} editable={!loading} onSubmitEditing={() => void crear()} returnKeyType="go" />
    <PasswordVisibility visible={visible} onPress={() => setVisible(!visible)} />
    <Notice message={error || sessionError} />
    <Button label="Crear cuenta" icon="arrow-forward" loading={loading} disabled={!API_URL} onPress={() => void crear()} />
    <Button label="Ya tengo una cuenta" variant="secondary" disabled={loading} onPress={() => router.replace('/login' as Href)} />
  </AuthFrame>;
}

const styles = StyleSheet.create({
  flex: { flex: 1 }, content: { flexGrow: 1, padding: 24, gap: 28, justifyContent: 'center', width: '100%', maxWidth: 510, alignSelf: 'center' },
  brand: { alignItems: 'center', gap: 14 }, logo: { width: 80, height: 80, borderRadius: 20 }, brandCopy: { width: '100%', minWidth: 0 }, brandTitle: { color: '#FFF', fontSize: 26, fontWeight: '800', letterSpacing: 0.6, textAlign: 'center' }, brandSubtitle: { color: '#94ACCB', fontSize: 12, lineHeight: 18, marginTop: 6, textAlign: 'center' },
  loginCard: { width: '100%', padding: 24, borderRadius: 23, gap: 15 }, cardIcon: { width: 47, height: 47, borderRadius: 15, backgroundColor: '#EAF2FF', justifyContent: 'center', alignItems: 'center' }, cardTitle: { fontSize: 24, color: colors.ink, fontWeight: '800', letterSpacing: -0.7 }, description: { color: colors.muted, fontSize: 13, lineHeight: 21, marginTop: -5, marginBottom: 4 },
  showPassword: { minHeight: 40, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 7 }, showText: { color: colors.muted, fontSize: 12 }, divider: { textAlign: 'center', fontSize: 12, color: colors.muted, paddingTop: 7 }, footer: { color: '#7891B3', textAlign: 'center', fontSize: 10, letterSpacing: 1.6 },
});
