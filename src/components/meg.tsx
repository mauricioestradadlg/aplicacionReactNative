import Ionicons from '@expo/vector-icons/Ionicons';
import type { ComponentProps, ReactNode } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Switch, Text, TextInput, View, type StyleProp, type TextInputProps, type ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export const colors = { primary: '#176CF2', ink: '#14233D', muted: '#6C7C94', background: '#F3F6FB', border: '#E3EAF4', success: '#168564', danger: '#C63546', white: '#FFFFFF' };
export const sharedStyles = StyleSheet.create({
  body: { fontSize: 15, color: colors.ink, lineHeight: 23 }, title: { fontSize: 20, fontWeight: '700', color: colors.ink },
  caption: { fontSize: 12, color: colors.muted, lineHeight: 19 }, row: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 10 },
});

export function Screen({ title, subtitle, children, refreshing = false, onRefresh, scroll = true }: { title: string; subtitle?: string; children: ReactNode; refreshing?: boolean; onRefresh?: () => void; scroll?: boolean }) {
  const heading = <View style={styles.heading}><Text style={styles.eyebrow}>PROYECTOS MEG · TU EQUIPO, CONECTADO</Text><Text accessibilityRole="header" style={styles.headingTitle}>{title}</Text>{subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}</View>;
  return <SafeAreaView edges={['left', 'right', 'bottom']} style={styles.safe}><KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={95}>
    {scroll ? <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" refreshControl={onRefresh ? <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} /> : undefined}>{heading}{children}<Text style={styles.footer}>Tu equipo, en movimiento.</Text></ScrollView> : <View style={[styles.content, styles.flex]}>{heading}{children}</View>}
  </KeyboardAvoidingView></SafeAreaView>;
}

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) { return <View style={[styles.card, style]}>{children}</View>; }
export function Button({ label, onPress, disabled, loading, variant = 'primary', icon }: { label: string; onPress: () => void; disabled?: boolean; loading?: boolean; variant?: 'primary' | 'secondary' | 'danger'; icon?: ComponentProps<typeof Ionicons>['name'] }) {
  const foreground = variant === 'secondary' ? colors.ink : colors.white;
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled: Boolean(disabled || loading), busy: loading }} disabled={disabled || loading} onPress={onPress} style={({ pressed }) => [styles.button, variant === 'secondary' && styles.secondary, variant === 'danger' && styles.danger, (disabled || loading) && styles.disabled, pressed && styles.pressed]}>
    {loading ? <ActivityIndicator color={foreground} size="small" /> : icon ? <Ionicons name={icon} color={foreground} size={18} /> : null}<Text style={[styles.buttonLabel, { color: foreground }]}>{label}</Text>
  </Pressable>;
}
export function Field({ label, style, ...props }: TextInputProps & { label: string }) { return <View style={styles.field}><Text style={styles.fieldLabel}>{label}</Text><TextInput accessibilityLabel={label} placeholderTextColor="#94A0B3" selectionColor={colors.primary} {...props} style={[styles.input, props.multiline && styles.multiline, props.editable === false && styles.disabled, style]} /></View>; }
export function Notice({ message, tone = 'error' }: { message?: string; tone?: 'error' | 'success' | 'info' }) {
  if (!message) return null;
  const tint = tone === 'error' ? colors.danger : tone === 'success' ? colors.success : colors.primary;
  return <View accessibilityRole={tone === 'error' ? 'alert' : undefined} accessibilityLiveRegion="polite" style={[styles.notice, { borderLeftColor: tint, backgroundColor: tone === 'error' ? '#FFF0F2' : tone === 'success' ? '#EAF7F1' : '#EBF3FF' }]}><Ionicons name={tone === 'error' ? 'alert-circle-outline' : 'information-circle-outline'} color={tint} size={19} /><Text style={[styles.noticeText, { color: tint }]}>{message}</Text></View>;
}
export function Chip({ label, selected, onPress }: { label: string; selected?: boolean; onPress?: () => void }) { return <Pressable accessibilityRole={onPress ? 'button' : 'text'} accessibilityState={{ selected }} onPress={onPress} disabled={!onPress} style={[styles.chip, selected && styles.chipSelected]}><Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text></Pressable>; }
export function Stat({ label, value, detail }: { label: string; value: string | number; detail?: string }) { return <View style={styles.stat}><Text style={styles.statLabel}>{label}</Text><Text style={styles.statValue}>{value}</Text>{detail && <Text style={sharedStyles.caption}>{detail}</Text>}</View>; }
export function Row({ children }: { children: ReactNode }) { return <View style={sharedStyles.row}>{children}</View>; }
export function SectionTitle({ children }: { children: ReactNode }) { return <Text accessibilityRole="header" style={styles.sectionTitle}>{children}</Text>; }
export function Empty({ message = 'Todavía no hay registros que mostrar.' }: { message?: string }) { return <View style={styles.empty}><Ionicons name="file-tray-outline" size={32} color={colors.muted} /><Text style={styles.emptyText}>{message}</Text></View>; }
export function Pagination({ pagina, paginas, onChange }: { pagina: number; paginas: number; onChange: (pagina: number) => void }) { if (paginas <= 1) return null; return <View style={styles.pagination}><Button label="Anterior" variant="secondary" disabled={pagina <= 1} onPress={() => onChange(pagina - 1)} /><Text style={sharedStyles.caption}>{pagina} de {paginas}</Text><Button label="Siguiente" variant="secondary" disabled={pagina >= paginas} onPress={() => onChange(pagina + 1)} /></View>; }
export function Toggle({ label, value, onValueChange, disabled }: { label: string; value: boolean; onValueChange: (value: boolean) => void; disabled?: boolean }) { return <View style={styles.toggle}><Text style={[sharedStyles.body, styles.flex]}>{label}</Text><Switch accessibilityLabel={label} value={value} disabled={disabled} onValueChange={onValueChange} trackColor={{ false: '#D4DEEB', true: colors.primary }} thumbColor="#FFFFFF" /></View>; }
export function Loading() { return <View style={styles.empty}><ActivityIndicator size="large" color={colors.primary} /><Text style={styles.emptyText}>Consultando el sistema…</Text></View>; }

const styles = StyleSheet.create({
  flex: { flex: 1 }, safe: { flex: 1, backgroundColor: colors.background }, content: { padding: 20, gap: 16, width: '100%', maxWidth: 1060, alignSelf: 'center', flexGrow: 1 },
  heading: { gap: 8, paddingTop: 8, paddingBottom: 8 }, eyebrow: { fontSize: 10, letterSpacing: 1.7, fontWeight: '700', color: colors.primary }, headingTitle: { fontSize: 29, fontWeight: '800', letterSpacing: -1, color: colors.ink }, subtitle: { fontSize: 14, lineHeight: 22, color: colors.muted },
  card: { minWidth: 0, padding: 20, borderWidth: 1, borderColor: colors.border, borderRadius: 20, backgroundColor: colors.white, gap: 14 },
  button: { minHeight: 48, paddingVertical: 12, paddingHorizontal: 18, borderRadius: 12, backgroundColor: colors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 9 }, secondary: { backgroundColor: '#EBF0F8' }, danger: { backgroundColor: colors.danger }, buttonLabel: { fontSize: 14, fontWeight: '700', textAlign: 'center', flexShrink: 1 }, disabled: { opacity: 0.5 }, pressed: { opacity: 0.8 },
  field: { gap: 7, minWidth: 0 }, fieldLabel: { fontSize: 13, fontWeight: '600', color: colors.ink }, input: { width: '100%', minWidth: 0, minHeight: 50, paddingHorizontal: 14, paddingVertical: 12, borderColor: colors.border, borderWidth: 1, borderRadius: 11, backgroundColor: '#FAFCFF', color: colors.ink, fontSize: 15 }, multiline: { minHeight: 100, textAlignVertical: 'top' },
  notice: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, borderLeftWidth: 3, padding: 14, borderRadius: 10 }, noticeText: { fontSize: 13, lineHeight: 21, flex: 1 },
  chip: { borderRadius: 9, paddingVertical: 10, paddingHorizontal: 13, minHeight: 40, justifyContent: 'center', backgroundColor: '#EAF0F8', borderWidth: 1, borderColor: '#EAF0F8' }, chipSelected: { backgroundColor: '#E8F1FF', borderColor: '#AACBFF' }, chipText: { fontSize: 12, fontWeight: '600', color: colors.muted }, chipTextSelected: { color: colors.primary },
  stat: { flexGrow: 1, flexBasis: 145, gap: 7, padding: 18, backgroundColor: colors.white, borderColor: colors.border, borderWidth: 1, borderRadius: 17 }, statLabel: { fontSize: 12, color: colors.muted, fontWeight: '600' }, statValue: { fontSize: 25, color: colors.ink, fontWeight: '800', letterSpacing: -0.6 },
  sectionTitle: { fontSize: 18, fontWeight: '700', color: colors.ink, marginTop: 4 }, empty: { alignItems: 'center', justifyContent: 'center', padding: 30, gap: 14 }, emptyText: { textAlign: 'center', color: colors.muted, fontSize: 14, lineHeight: 23 }, pagination: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 10, paddingVertical: 12 }, toggle: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 48 }, footer: { fontSize: 11, color: '#8E9BB0', textAlign: 'center', paddingTop: 16, paddingBottom: 10 },
});
