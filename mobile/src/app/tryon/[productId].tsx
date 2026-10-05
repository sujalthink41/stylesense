import * as Crypto from 'expo-crypto';
import * as Haptics from 'expo-haptics';
import { Image } from 'expo-image';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { friendlyMessage } from '@/api/errors';
import { api } from '@/auth/session';
import { useTheme } from '@/design/theme';
import { palette, radius, space } from '@/design/tokens';
import { saveImage, shareFromUrl } from '@/media/save';
import { pickPhoto, uploadPhoto } from '@/media/upload';
import { Buti } from '@/ui/atoms/Buti';
import { BackButton } from '@/ui/atoms/BackButton';
import { Button } from '@/ui/atoms/Button';
import { Icon } from '@/ui/atoms/Icon';
import { Text } from '@/ui/atoms/Text';
import { Banner } from '@/ui/molecules/Banner';
import { PrintRepeat } from '@/ui/molecules/PrintRepeat';
import { enter, Rise } from '@/ui/motion';

interface TryOn {
  id: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  result_url?: string | null;
  error?: string | null;
  retryable: boolean;
}

type Stage = { kind: 'intro' } | { kind: 'uploading' } | { kind: 'rendering'; job: TryOn } | { kind: 'done'; job: TryOn } | { kind: 'failed'; job?: TryOn; message: string };

const POLL_MS = 1_500;
const POLL_LIMIT = 60; // ~90 s; the worker retries a busy vendor up to 3 times

export default function TryOnScreen() {
  const { productId, title } = useLocalSearchParams<{ productId: string; title?: string }>();
  const { colors } = useTheme();
  const [stage, setStage] = useState<Stage>({ kind: 'intro' });
  const alive = useRef(true);
  useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );

  const follow = async (job: TryOn) => {
    for (let i = 0; i < POLL_LIMIT && alive.current; i++) {
      if (job.status === 'done') {
        void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        return setStage({ kind: 'done', job });
      }
      if (job.status === 'failed') return setStage({ kind: 'failed', job, message: job.error ?? 'The try-on didn’t work this time.' });
      setStage({ kind: 'rendering', job });
      await new Promise((r) => setTimeout(r, POLL_MS));
      job = await api.get<TryOn>(`/v1/tryon/${job.id}`);
    }
    if (alive.current) setStage({ kind: 'failed', job, message: 'This is taking longer than usual. Check back in a minute.' });
  };

  const start = async (source: 'camera' | 'library') => {
    try {
      const uri = await pickPhoto(source, 'selfie');
      if (!uri) return;
      setStage({ kind: 'uploading' });
      const selfie = await uploadPhoto(uri, 'selfie');
      // One key per attempt: a double tap or a retried request can't start (or pay for) two jobs.
      const job = await api.post<TryOn>(
        '/v1/tryon',
        { selfie_upload_id: selfie.id, product_id: productId },
        { headers: { 'Idempotency-Key': Crypto.randomUUID() } },
      );
      await follow(job);
    } catch (error) {
      setStage({ kind: 'failed', message: friendlyMessage(error) });
    }
  };

  const retry = async (job: TryOn) => {
    try {
      await follow(await api.post<TryOn>(`/v1/tryon/${job.id}/retry`));
    } catch (error) {
      setStage({ kind: 'failed', job, message: friendlyMessage(error) });
    }
  };

  const report = async (job: TryOn) => {
    try {
      await api.post('/v1/reports', { target_kind: 'tryon', target_id: job.id, reason: 'inappropriate' });
      setStage({ kind: 'failed', job: { ...job, retryable: false }, message: 'Thanks. We’ve hidden this result and will look at it.' });
    } catch (error) {
      setStage({ kind: 'done', job }); // keep the result; say the report didn't go through
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      console.warn('report failed', friendlyMessage(error));
    }
  };

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.shell }]} edges={['top', 'bottom']}>
      <View style={styles.top}>
        <BackButton close variant="glass" label="Close try-on" />
        <Text variant="bodySmall" tone="onShellMuted" numberOfLines={1} style={{ flex: 1 }}>
          {title ?? 'Virtual try-on'}
        </Text>
      </View>

      {stage.kind === 'intro' ? (
        <View style={styles.body}>
          <Rise index={0} style={styles.hero}>
            <View style={[styles.frame, { borderColor: palette.indigo500 }]}>
              <Buti size={120} color={palette.indigo700} />
              <Icon name="camera" size={40} color={palette.turmeric} />
            </View>
          </Rise>
          <Rise index={1} style={{ gap: 10 }}>
            <Text variant="displayXL" tone="onShell" accessibilityRole="header" style={{ fontSize: 42, lineHeight: 44 }}>
              See it on you.
            </Text>
            <Text variant="body" tone="onShellMuted">
              A clear, front-facing photo works best: good light, arms by your sides. Your photo and the result are deleted within 24 hours.
            </Text>
          </Rise>
          <Rise index={2} style={{ gap: 8 }}>
            <Button label="Take a selfie" variant="inverse" size="lg" icon="camera" fullWidth onPress={() => void start('camera')} />
            <Button label="Choose from photos" variant="ghost" fullWidth onPress={() => void start('library')} />
          </Rise>
        </View>
      ) : null}

      {stage.kind === 'uploading' || stage.kind === 'rendering' ? (
        <View style={styles.body}>
          <PrintRepeat label={stage.kind === 'uploading' ? 'Uploading your photo…' : stage.job.status === 'queued' ? 'In the queue…' : 'Dressing you…'} rows={4} />
          <Text variant="bodySmall" tone="onShellMuted" align="center">
            This usually takes under a minute. You can leave; we’ll keep going.
          </Text>
        </View>
      ) : null}

      {stage.kind === 'done' && stage.job.result_url ? <Result job={stage.job} onReport={() => void report(stage.job)} /> : null}

      {stage.kind === 'failed' ? (
        <View style={styles.body}>
          <Banner tone="warning" text={stage.message} />
          {stage.job?.retryable ? <Button label="Try again (free)" variant="inverse" fullWidth onPress={() => void retry(stage.job!)} /> : null}
          <Button label="Use another photo" variant="ghost" fullWidth onPress={() => setStage({ kind: 'intro' })} />
        </View>
      ) : null}
    </SafeAreaView>
  );
}

/** The result is revealed top to bottom, like a print lifted off the block. */
function Result({ job, onReport }: { job: TryOn; onReport(): void }) {
  const reveal = useSharedValue(0);
  const [note, setNote] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    reveal.set(withTiming(1, { duration: 900, easing: Easing.out(Easing.cubic) }));
  }, [reveal]);
  const mask = useAnimatedStyle(() => ({ height: `${reveal.value * 100}%` }));
  const name = `stylesense-look-${job.id}.jpg`;

  const save = async () => {
    setSaving(true);
    try {
      const outcome = await saveImage(job.result_url!, name);
      if (outcome === 'saved') {
        void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        setNote('Saved to your gallery.');
      } else if (outcome === 'shared') setNote('Choose “Save” in the share sheet to keep it.');
    } catch {
      setNote('Couldn’t save just now. Try Share instead.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.body}>
      <View style={styles.result}>
        <Animated.View style={[styles.mask, mask]}>
          <Image source={{ uri: job.result_url! }} style={styles.resultImage} contentFit="cover" accessibilityLabel="You, wearing this item" />
        </Animated.View>
      </View>
      {note ? (
        <Animated.View entering={enter.pop()}>
          <Text variant="bodySmall" tone="onShell" align="center">
            {note}
          </Text>
        </Animated.View>
      ) : null}
      <Animated.View entering={enter.rise(2)} style={{ gap: 8 }}>
        <Button label="Save to Photos" variant="inverse" icon="download" fullWidth loading={saving} onPress={() => void save()} />
        <View style={styles.row}>
          <Button
            label="Share"
            variant="ghost"
            icon="share"
            style={{ flex: 1 }}
            onPress={() => void shareFromUrl(job.result_url!, name).catch(() => setNote('Couldn’t open sharing.'))}
          />
          <Button label="Done" variant="ghost" style={{ flex: 1 }} onPress={() => router.back()} />
        </View>
        <Button label="Report this result" variant="ghost" onPress={onReport} />
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  top: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: space.screen, paddingVertical: space.xs },
  body: { flex: 1, padding: space.screen, gap: space.lg, justifyContent: 'center' },
  hero: { alignItems: 'center' },
  frame: { width: 200, height: 250, borderRadius: radius.xl, borderWidth: 2, borderStyle: 'dashed', alignItems: 'center', justifyContent: 'center', gap: 8 },
  result: { flex: 1, borderRadius: radius.xl, overflow: 'hidden', backgroundColor: palette.indigo700 },
  mask: { overflow: 'hidden', width: '100%' },
  resultImage: { width: '100%', aspectRatio: 2 / 3 },
  row: { flexDirection: 'row', gap: 10 },
});
