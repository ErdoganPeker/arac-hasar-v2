import React, { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';

import { AuthScreenProps } from '../navigation/types';
import { useAuth } from '../services/AuthContext';
import { describeError } from '../services/api';
import UploadButton from '../components/UploadButton';
import { colors, radius, spacing, typography } from '../theme';

type Props = AuthScreenProps<'Register'>;

const EMAIL_RE = /\S+@\S+\.\S+/;

export default function RegisterScreen({ navigation }: Props) {
  const { t } = useTranslation(['auth', 'common']);
  const { register } = useAuth();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);
    if (!EMAIL_RE.test(email.trim())) {
      setError(t('auth:emailInvalid'));
      return;
    }
    if (password.length < 8) {
      setError(t('auth:passwordTooShort'));
      return;
    }
    if (password !== passwordConfirm) {
      setError(t('auth:passwordMismatch'));
      return;
    }
    setLoading(true);
    try {
      await register({
        email: email.trim(),
        password,
        full_name: fullName.trim() || undefined,
        company: company.trim() || undefined,
      });
    } catch (e) {
      const msg = describeError(e);
      setError(msg === 'networkError' ? t('common:networkError') : msg || t('common:unknownError'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 24}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.subtitle}>{t('auth:registerSubtitle')}</Text>

          <Field label={t('auth:fullName')}>
            <TextInput
              style={styles.input}
              value={fullName}
              onChangeText={setFullName}
              placeholder={t('auth:fullNamePlaceholder')}
              placeholderTextColor={colors.textDim}
              autoCapitalize="words"
              textContentType="name"
            />
          </Field>

          <Field label={t('auth:email')}>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder={t('auth:emailPlaceholder')}
              placeholderTextColor={colors.textDim}
              keyboardType="email-address"
              autoCapitalize="none"
              autoComplete="email"
              textContentType="emailAddress"
            />
          </Field>

          <Field label={t('auth:company')}>
            <TextInput
              style={styles.input}
              value={company}
              onChangeText={setCompany}
              placeholderTextColor={colors.textDim}
            />
          </Field>

          <Field label={t('auth:password')}>
            <TextInput
              style={styles.input}
              value={password}
              onChangeText={setPassword}
              placeholder={t('auth:passwordPlaceholder')}
              placeholderTextColor={colors.textDim}
              secureTextEntry
              textContentType="newPassword"
            />
          </Field>

          <Field label={t('auth:passwordConfirm')}>
            <TextInput
              style={styles.input}
              value={passwordConfirm}
              onChangeText={setPasswordConfirm}
              placeholderTextColor={colors.textDim}
              secureTextEntry
              textContentType="newPassword"
            />
          </Field>

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <UploadButton
            label={loading ? t('auth:registering') : t('auth:registerButton')}
            onPress={handleSubmit}
            loading={loading}
            style={styles.cta}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xxl },
  subtitle: { ...typography.body, color: colors.textMuted, marginBottom: spacing.xxl },
  field: { marginBottom: spacing.lg },
  label: { ...typography.label, color: colors.textMuted, marginBottom: spacing.xs },
  input: {
    backgroundColor: colors.bgInput,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    color: colors.text,
    ...typography.body,
  },
  error: { ...typography.caption, color: colors.danger, marginBottom: spacing.sm },
  cta: { marginTop: spacing.md },
});
