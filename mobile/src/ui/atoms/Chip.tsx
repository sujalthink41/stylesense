import * as Haptics from 'expo-haptics';
import { StyleSheet } from 'react-native';

import { useTheme } from '@/design/theme';
import { radius } from '@/design/tokens';

import { Icon } from './Icon';
import { PressableScale } from './PressableScale';
import { Text } from './Text';

export interface ChipProps {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  disabled?: boolean;
  /** On the indigo shell (home band, sign-in). */
  onShell?: boolean;
  /** Square-ish option tile used by question cards, instead of a pill. */
  shape?: 'pill' | 'tile';
  testID?: string;
}

export function Chip({ label, selected = false, onPress, disabled, onShell, shape = 'pill', testID }: ChipProps) {
  const { colors, elevation } = useTheme();
  const bg = onShell
    ? selected
      ? colors.ground
      : colors.shellRaised
    : selected
      ? colors.shell
      : shape === 'tile'
        ? colors.ground
        : colors.raised;
  const tone = onShell ? (selected ? 'onTonal' : 'onShell') : selected ? 'onShell' : disabled ? 'disabled' : 'default';
  return (
    <PressableScale
      testID={testID}
      accessibilityRole="checkbox"
      accessibilityState={{ checked: selected, disabled: !!disabled }}
      accessibilityLabel={label}
      disabled={disabled}
      onPress={() => {
        void Haptics.selectionAsync();
        onPress?.();
      }}
      style={[
        shape === 'tile' ? styles.tile : styles.pill,
        { backgroundColor: disabled ? colors.tonal : bg },
        !selected && !onShell && shape === 'pill' && elevation(1),
      ]}
    >
      {selected && !onShell && shape === 'pill' ? (
        <Icon name="check" size={17} color={colors.bestPrice} strokeWidth={2.6} />
      ) : null}
      <Text variant="label" tone={tone} numberOfLines={1}>
        {label}
      </Text>
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  pill: {
    minHeight: 44,
    paddingHorizontal: 18,
    borderRadius: radius.pill,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  tile: {
    minHeight: 52,
    paddingHorizontal: 14,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    flexGrow: 1,
    flexBasis: '45%',
  },
});
