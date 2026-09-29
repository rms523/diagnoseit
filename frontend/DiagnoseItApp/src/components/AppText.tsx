import React from 'react';
import { Text, StyleSheet, TextStyle, StyleProp } from 'react-native';
import { tokens, fonts } from '../theme/tokens';

type Variant = 'eyebrow' | 'display' | 'title' | 'body' | 'caption' | 'mono';

interface AppTextProps {
  variant?: Variant;
  children: React.ReactNode;
  style?: StyleProp<TextStyle>;
  numberOfLines?: number;
}

const variantStyles: Record<Variant, object> = {
  eyebrow: {
    fontFamily: fonts.bodySemiBold,
    fontSize: 11,
    letterSpacing: 1.2,
    textTransform: 'uppercase' as const,
    color: tokens.teal,
  },
  display: {
    fontFamily: fonts.display,
    fontSize: 28,
    color: tokens.ink,
  },
  title: {
    fontFamily: fonts.bodySemiBold,
    fontSize: 20,
    color: tokens.ink,
  },
  body: {
    fontFamily: fonts.body,
    fontSize: 15,
    color: tokens.inkSecondary,
    lineHeight: 22,
  },
  caption: {
    fontFamily: fonts.body,
    fontSize: 12,
    color: tokens.inkMuted,
  },
  mono: {
    fontFamily: fonts.mono,
    fontSize: 12,
    color: tokens.inkMuted,
  },
};

export const AppText: React.FC<AppTextProps> = ({
  variant = 'body',
  children,
  style,
  numberOfLines,
}) => (
  <Text style={[variantStyles[variant], style]} numberOfLines={numberOfLines}>
    {children}
  </Text>
);

/** Shared card surface styling */
export const cardStyle = StyleSheet.create({
  surface: {
    backgroundColor: tokens.paperElevated,
    borderRadius: tokens.radiusLg,
    borderWidth: 1,
    borderColor: tokens.paperInset,
  },
});

export default AppText;
