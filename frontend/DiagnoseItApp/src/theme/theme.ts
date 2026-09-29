import { MD3LightTheme } from 'react-native-paper';
import type { MD3Theme } from 'react-native-paper';
import { tokens } from './tokens';

export { tokens, fonts } from './tokens';

export const theme: MD3Theme = {
  ...MD3LightTheme,
  roundness: tokens.radiusMd,
  colors: {
    ...MD3LightTheme.colors,
    primary: tokens.teal,
    primaryContainer: tokens.tealDim,
    secondary: tokens.slate,
    secondaryContainer: tokens.slateDim,
    tertiary: tokens.sage,
    tertiaryContainer: tokens.sageDim,
    surface: tokens.paperElevated,
    surfaceVariant: tokens.paperMuted,
    background: tokens.paper,
    error: tokens.coral,
    errorContainer: tokens.coralDim,
    onPrimary: tokens.paperElevated,
    onSecondary: tokens.paperElevated,
    onTertiary: tokens.paperElevated,
    onSurface: tokens.ink,
    onSurfaceVariant: tokens.inkMuted,
    onBackground: tokens.ink,
    onError: tokens.paperElevated,
    outline: tokens.paperInset,
    outlineVariant: tokens.paperMuted,
    shadow: tokens.ink,
    scrim: tokens.ink,
    inverseSurface: tokens.ink,
    inverseOnSurface: tokens.paper,
    inversePrimary: tokens.tealLight,
    elevation: {
      level0: 'transparent',
      level1: tokens.paperElevated,
      level2: tokens.paperElevated,
      level3: tokens.paperElevated,
      level4: tokens.paperElevated,
      level5: tokens.paperElevated,
    },
  },
};

export const navigationTheme = {
  dark: false,
  colors: {
    primary: tokens.teal,
    background: tokens.paper,
    card: tokens.paperElevated,
    text: tokens.ink,
    border: tokens.paperInset,
    notification: tokens.coral,
  },
};
