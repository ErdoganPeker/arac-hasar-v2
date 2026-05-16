import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';

import { AuthScreenProps } from '../navigation/types';
import UploadButton from '../components/UploadButton';
import { colors, spacing, typography } from '../theme';

type Props = AuthScreenProps<'ForgotPassword'>;

export default function ForgotPasswordScreen({ navigation }: Props) {
  const { t } = useTranslation(['auth', 'common']);
  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <View style={styles.wrap}>
        <Text style={styles.title}>{t('auth:forgotTitle')}</Text>
        <Text style={styles.body}>{t('auth:forgotDescription')}</Text>
        <UploadButton
          label={t('common:back')}
          variant="secondary"
          onPress={() => navigation.goBack()}
          style={{ marginTop: spacing.xl }}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  wrap: {
    flex: 1,
    padding: spacing.xxl,
    justifyContent: 'center',
  },
  title: { ...typography.h1, color: colors.text, marginBottom: spacing.md },
  body: { ...typography.body, color: colors.textMuted },
});
