import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { friendlyMessage } from '@/api/errors';
import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { pickPhoto, uploadPhoto } from '@/media/upload';
import { useStylist } from '@/stylist';
import { Buti } from '@/ui/atoms/Buti';
import { BackButton } from '@/ui/atoms/BackButton';
import { Button } from '@/ui/atoms/Button';
import { Icon } from '@/ui/atoms/Icon';
import { Text } from '@/ui/atoms/Text';
import { Banner } from '@/ui/molecules/Banner';
import { Rise } from '@/ui/motion';

/** Shop from a photo: snap a look you like, get the closest pieces across every store. */
export default function PhotoScreen() {
  const { colors } = useTheme();
  const start = useStylist((s) => s.start);
  const [uri, setUri] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const go = async (source: 'camera' | 'library') => {
    setError(null);
    try {
      const picked = await pickPhoto(source, 'photo_search');
      if (!picked) return;
      setUri(picked);
      setStatus('Reading the photo…');
      const upload = await uploadPhoto(picked, 'photo_search');
      setStatus('Finding it in every store…');
      const id = await start('photo', upload.id);
      if (id) router.replace(`/session/${id}`);
      else setStatus(null);
    } catch (e) {
      setStatus(null);
      setError(friendlyMessage(e));
    }
  };

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.ground }]} edges={['top', 'bottom']}>
      <View style={styles.top}>
        <BackButton close />
      </View>
      <View style={styles.body}>
        <Rise index={0} style={[styles.frame, { backgroundColor: colors.shell }]}>
          {uri ? (
            <>
              <Image source={{ uri }} style={StyleSheet.absoluteFill} contentFit="cover" />
              {status ? <Scanner /> : null}
            </>
          ) : (
            <View style={styles.placeholder}>
              <Buti size={140} color={palette.indigo700} />
              <View style={styles.cameraBadge}>
                <Icon name="camera" size={34} color={palette.ink} />
              </View>
            </View>
          )}
        </Rise>
        <Rise index={1} style={{ gap: 8 }}>
          <Text variant="displayXL" accessibilityRole="header" style={{ fontSize: 40, lineHeight: 42 }}>
            {status ?? 'Shop the look.'}
          </Text>
          <Text variant="body" tone="secondary">
            Snap an outfit, a screenshot or a shop window. We find the closest pieces on Amazon, Flipkart and Myntra. Photos are deleted within 24 hours.
          </Text>
        </Rise>
        {error ? <Banner tone="warning" text={error} /> : null}
        <Rise index={2} style={{ gap: 8 }}>
          <Button label="Take a photo" variant="primary" size="lg" icon="camera" fullWidth loading={!!status} onPress={() => void go('camera')} />
          <Button label="Choose from gallery" variant="ghost" fullWidth disabled={!!status} onPress={() => void go('library')} />
        </Rise>
      </View>
    </SafeAreaView>
  );
}

/** A turmeric line sweeping the photo while it's read. */
function Scanner() {
  const y = useSharedValue(0);
  useEffect(() => {
    y.set(withRepeat(withTiming(1, { duration: 1400, easing: Easing.inOut(Easing.quad) }), -1, true));
  }, [y]);
  const line = useAnimatedStyle(() => ({ top: `${y.value * 96}%` }));
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      <View style={[StyleSheet.absoluteFill, { backgroundColor: 'rgba(15,22,51,0.35)' }]} />
      <Animated.View style={[styles.scan, line]} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  top: { paddingHorizontal: space.screen, paddingVertical: space.xs },
  body: { flex: 1, padding: space.screen, gap: space.lg, justifyContent: 'flex-end' },
  frame: { flex: 1, borderRadius: radius.xl, overflow: 'hidden' },
  placeholder: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  cameraBadge: { position: 'absolute', width: 72, height: 72, borderRadius: 36, backgroundColor: palette.turmeric, alignItems: 'center', justifyContent: 'center' },
  scan: { position: 'absolute', left: 0, right: 0, height: 3, backgroundColor: palette.turmeric, boxShadow: '0 0 16px 4px rgba(217,162,27,0.7)' },
});
