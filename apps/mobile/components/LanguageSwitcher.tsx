import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { colors, radius, spacing, typography } from '../theme';
import { changeLanguage, SupportedLocale } from '../i18n';

interface Props {
  compact?: boolean;
}

export default function LanguageSwitcher({ compact }: Props) {
  const { i18n, t } = useTranslation('common');

  const set = async (locale: SupportedLocale) => {
    await changeLanguage(locale);
  };

  const current = (i18n.language || 'tr').toLowerCase().startsWith('en') ? 'en' : 'tr';

  return (
    <View style={[styles.wrap, compact && styles.wrapCompact]}>
      <Pressable
        accessibilityRole="button"
        onPress={() => set('tr')}
        style={[styles.btn, current === 'tr' && styles.btnActive]}
      >
        <Text style={[styles.text, current === 'tr' && styles.textActive]}>
          {compact ? 'TR' : t('languageTr')}
        </Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        onPress={() => set('en')}
        style={[styles.btn, current === 'en' && styles.btnActive]}
      >
        <Text style={[styles.text, current === 'en' && styles.textActive]}>
          {compact ? 'EN' : t('languageEn')}
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    backgroundColor: colors.bgElevated,
    borderRadius: radius.pill,
    padding: 4,
    alignSelf: 'flex-start',
  },
  wrapCompact: {
    padding: 2,
  },
  btn: {
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
  },
  btnActive: {
    backgroundColor: colors.primary,
  },
  text: {
    ...typography.caption,
    color: colors.textMuted,
    fontWeight: '600',
  },
  textActive: {
    color: '#fff',
  },
});
