import React, { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
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
import LanguageSwitcher from '../components/LanguageSwitcher';
import { colors, radius, spacing, typography } from '../theme';

type Props = AuthScreenProps<'Login'>;

const EMAIL_RE = /\S+@\S+\.\S+/;

export default function LoginScreen({ navigation }: Props) {
  const { t } = useTranslation(['auth', 'common']);
  const { signIn } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async () => {
    setError(null);
    if (!email.trim()) {
      setError(t('auth:emailRequired'));
      return;
    }
    if (!EMAIL_RE.test(email.trim())) {
      setError(t('auth:emailInvalid'));
      return;
    }
    if (!password) {
      setError(t('auth:passwordRequired'));
      return;
    }
    setLoading(true);
    try {
      await signIn({ email: email.trim(), password });
    } catch (e) {
      const msg = describeError(e);
      // Map known errors to localized strings when possible.
      const localized =
        msg === 'networkError'
          ? t('common:networkError')
          : msg.toLowerCase().includes('invalid') || msg.toLowerCase().includes('credentials')
            ? t('auth:invalidCredentials')
            : msg || t('common:unknownError');
      setError(localized);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 24}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.header}>
            <Text style={styles.brand}>{t('common:appName')}</Text>
            <LanguageSwitcher compact />
          </View>

          <Text style={styles.title}>{t('auth:loginTitle')}</Text>
          <Text style={styles.subtitle}>{t('auth:loginSubtitle')}</Text>

          <View style={styles.field}>
            <Text style={styles.label}>{t('auth:email')}</Text>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder={t('auth:emailPlaceholder')}
              placeholderTextColor={colors.textDim}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="email"
              textContentType="emailAddress"
              returnKeyType="next"
            />
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>{t('auth:password')}</Text>
            <TextInput
              style={styles.input}
              value={password}
              onChangeText={setPassword}
              placeholder={t('auth:passwordPlaceholder')}
              placeholderTextColor={colors.textDim}
              secureTextEntry
              autoComplete="password"
              textContentType="password"
              returnKeyType="go"
              onSubmitEditing={handleLogin}
            />
          </View>

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <UploadButton
            label={loading ? t('auth:loggingIn') : t('auth:loginButton')}
            onPress={handleLogin}
            loading={loading}
            style={styles.cta}
          />

          <Pressable
            accessibilityRole="button"
            onPress={() => navigation.navigate('ForgotPassword')}
            style={styles.forgotWrap}
          >
            <Text style={styles.forgot}>{t('auth:forgotPassword')}</Text>
          </Pressable>

          <View style={styles.footer}>
            <Text style={styles.footerText}>{t('auth:noAccount')} </Text>
            <Pressable onPress={() => navigation.navigate('Register')}>
              <Text style={styles.footerLink}>{t('auth:createOne')}</Text>
            </Pressable>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: {
    padding: spacing.xxl,
    flexGrow: 1,
    justifyContent: 'center',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.xxxl,
  },
  brand: {
    ...typography.h1,
    color: colors.primaryLight,
  },
  title: { ...typography.display, color: colors.text, marginBottom: spacing.xs },
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
  cta: { marginTop: spacing.md },
  error: {
    ...typography.caption,
    color: colors.danger,
    marginBottom: spacing.sm,
  },
  forgotWrap: { alignSelf: 'flex-end', marginTop: spacing.md },
  forgot: { ...typography.caption, color: colors.primaryLight, fontWeight: '600' },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: spacing.xxl,
  },
  footerText: { ...typography.body, color: colors.textMuted },
  footerLink: { ...typography.body, color: colors.primaryLight, fontWeight: '600' },
});
