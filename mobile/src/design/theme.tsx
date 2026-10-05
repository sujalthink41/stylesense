import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useColorScheme } from 'react-native';

import { colors, elevation, type ColorScheme, type Colors } from './tokens';

export interface Theme {
  scheme: ColorScheme;
  colors: Colors;
  elevation: (level: 0 | 1 | 2 | 3) => { boxShadow?: string };
}

const ThemeContext = createContext<Theme | null>(null);

export function makeTheme(scheme: ColorScheme): Theme {
  return {
    scheme,
    colors: colors[scheme],
    elevation: (level) => elevation(level, scheme),
  };
}

/** Follows the phone's light/dark setting unless a scheme is forced (tests, previews). */
export function ThemeProvider({ children, scheme }: { children: ReactNode; scheme?: ColorScheme }) {
  const system = useColorScheme();
  const resolved: ColorScheme = scheme ?? (system === 'dark' ? 'dark' : 'light');
  const theme = useMemo(() => makeTheme(resolved), [resolved]);
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  const theme = useContext(ThemeContext);
  if (!theme) throw new Error('useTheme must be used inside <ThemeProvider>');
  return theme;
}
