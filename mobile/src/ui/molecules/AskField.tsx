import { useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { useTheme } from '@/design/theme';
import { radius } from '@/design/tokens';
import { typeScale } from '@/design/typography';
import { Icon } from '@/ui/atoms/Icon';
import { IconButton } from '@/ui/atoms/IconButton';

export interface AskFieldProps {
  placeholder: string;
  onSubmit(text: string): void;
  onPhoto?: () => void;
  disabled?: boolean;
  /** Indigo band (home) or cotton ground (session composer). */
  surface?: 'shell' | 'ground';
  testID?: string;
}

/** The free-text door to the stylist. Optional by design: every screen also offers taps. */
export function AskField({ placeholder, onSubmit, onPhoto, disabled, surface = 'shell', testID }: AskFieldProps) {
  const { colors, elevation } = useTheme();
  const [text, setText] = useState('');
  const onShell = surface === 'shell';
  const submit = () => {
    const value = text.trim();
    if (!value || disabled) return;
    onSubmit(value);
    setText('');
  };
  return (
    <View
      style={[
        styles.field,
        { backgroundColor: onShell ? colors.shellRaised : colors.raised },
        !onShell && elevation(2),
      ]}
    >
      <Icon name="search" size={20} color={onShell ? colors.onShellMuted : colors.textSecondary} />
      <TextInput
        testID={testID}
        value={text}
        onChangeText={setText}
        onSubmitEditing={submit}
        returnKeyType="send"
        editable={!disabled}
        placeholder={placeholder}
        placeholderTextColor={onShell ? '#AEB5D4' : colors.textSecondary}
        accessibilityLabel="Ask the stylist"
        style={[typeScale.body, styles.input, { color: onShell ? colors.onShell : colors.text }]}
        selectionColor={colors.focus}
        maxLength={500}
      />
      {text.trim() ? (
        <IconButton icon="arrowRight" label="Send" size={44} variant={onShell ? 'shell' : 'tonal'} onPress={submit} />
      ) : onPhoto ? (
        <IconButton icon="camera" label="Search with a photo" size={44} variant={onShell ? 'shell' : 'tonal'} onPress={onPhoto} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  field: {
    minHeight: 56,
    borderRadius: radius.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingLeft: 16,
    paddingRight: 6,
  },
  input: { flex: 1, minWidth: 0, paddingVertical: 14 },
});
