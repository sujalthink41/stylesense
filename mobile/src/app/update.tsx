import * as Linking from 'expo-linking';
import { StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useTheme } from '@/design/theme';
import { space } from '@/design/tokens';
import { LogoMark } from '@/ui/atoms/Buti';
import { Button } from '@/ui/atoms/Button';
import { Text } from '@/ui/atoms/Text';

const STORE_URL = 'https://play.google.com/store/apps/details?id=com.stylesense.app';

/** Shown when this version is below the minimum the server supports. */
export default function UpdateScreen() {
  const { colors } = useTheme();
  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.shell }]}>
      <View style={styles.body}>
        <LogoMark size={56} block={colors.ground} ink={colors.shell} eye={colors.action} />
        <Text variant="display" tone="onShell">
          A newer StyleSense is ready
        </Text>
        <Text variant="body" tone="onShellMuted">
          This version can’t talk to our servers any more. Update to keep your picks, boards and taste.
        </Text>
      </View>
      <Button label="Update now" variant="inverse" onPress={() => void Linking.openURL(STORE_URL)} fullWidth />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: space.lg, justifyContent: 'space-between' },
  body: { gap: space.md, marginTop: space.xxl },
});
