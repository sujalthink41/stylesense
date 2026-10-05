import { useState } from 'react';
import { KeyboardAvoidingView, Platform, StyleSheet, TextInput, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { DEV_SIGN_IN } from '@/api/config';
import { friendlyMessage } from '@/api/errors';
import { useSession } from '@/auth/session';
import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { typeScale } from '@/design/typography';
import { Buti, LogoMark } from '@/ui/atoms/Buti';
import { Button } from '@/ui/atoms/Button';
import { Text } from '@/ui/atoms/Text';

export default function SignInScreen() {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const signInWithDev = useSession((s) => s.signInWithDev);
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const devSignIn = async () => {
    if (!email.includes('@')) {
      setError('Enter an email address to sign in.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await signInWithDev(email);
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={[styles.screen, { backgroundColor: colors.shell }]}>
      <PrintedField width={width} />
      <SafeAreaView style={styles.safe}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.bottom}>
          <View style={styles.brand}>
            <LogoMark size={36} block={palette.cotton} ink={palette.indigo} eye={palette.madder} />
            <Text variant="headline" tone="onShell" style={{ fontFamily: 'AnekLatinCondensed-Bold', fontSize: 26 }}>
              StyleSense
            </Text>
          </View>
          <View style={styles.copy}>
            <Text variant="displayXL" tone="onShell" accessibilityRole="header" style={{ fontSize: 54, lineHeight: 54 }}>
              Your stylist.{'\n'}Your budget.{'\n'}
              <Text variant="displayXL" style={{ color: palette.turmeric, fontSize: 54, lineHeight: 54 }}>
                Every store.
              </Text>
            </Text>
            <Text variant="body" tone="onShellMuted" style={{ maxWidth: 320 }}>
              Tap what you’re dressing for. We compare Amazon, Flipkart and Myntra and keep every pick inside your budget.
            </Text>
          </View>

          {DEV_SIGN_IN ? (
            <View style={styles.dev}>
              <TextInput
                value={email}
                onChangeText={setEmail}
                placeholder="you@example.com"
                placeholderTextColor="#AEB5D4"
                autoCapitalize="none"
                autoComplete="email"
                keyboardType="email-address"
                accessibilityLabel="Email for developer sign-in"
                style={[typeScale.body, styles.input, { backgroundColor: colors.shellRaised, color: colors.onShell }]}
                onSubmitEditing={devSignIn}
                testID="dev-email"
              />
              <Button label="Continue" variant="inverse" loading={busy} onPress={devSignIn} fullWidth testID="dev-sign-in" />
              <Text variant="caption" tone="onShellMuted" align="center">
                Developer sign-in (this build only). Google sign-in arrives with the installable build.
              </Text>
            </View>
          ) : (
            <Button label="Continue with Google" variant="inverse" fullWidth disabled accessibilityHint="Available in the installable build" />
          )}
          {error ? (
            <Text variant="bodySmall" style={{ color: palette.madderTint }} accessibilityRole="alert">
              {error}
            </Text>
          ) : null}
          <Text variant="caption" tone="onShellMuted" align="center">
            Store links may earn us a commission. It never changes which picks you see.
          </Text>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </View>
  );
}

/** A printed block-repeat over the top of the screen: one turmeric impression among indigo. */
function PrintedField({ width }: { width: number }) {
  const cell = width / 4.3;
  const rows = 5;
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      {Array.from({ length: rows }, (_, r) => (
        <View key={r} style={{ flexDirection: 'row', marginLeft: r % 2 ? cell / 2 : 0, opacity: 1 - r * 0.17 }}>
          {Array.from({ length: 5 }, (_, c) => (
            <View key={c} style={{ width: cell, height: cell * 0.9, alignItems: 'center', justifyContent: 'center' }}>
              <Buti size={cell * 0.62} color={r === 2 && c === 3 ? palette.turmeric : palette.indigo700} />
            </View>
          ))}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  safe: { flex: 1, justifyContent: 'flex-end' },
  bottom: { paddingHorizontal: space.lg, paddingBottom: space.lg, gap: space.lg },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  copy: { gap: 14 },
  dev: { gap: space.sm },
  input: { height: 56, borderRadius: radius.md, paddingHorizontal: 16 },
});
