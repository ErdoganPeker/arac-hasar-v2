import React, { useState } from 'react';
import {
  Alert,
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

import { MainScreenProps } from '../navigation/types';
import { useAuth } from '../services/AuthContext';
import { api, describeError } from '../services/api';
import UploadButton from '../components/UploadButton';
import LanguageSwitcher from '../components/LanguageSwitcher';
import { colors, radius, spacing, typography } from '../theme';

type Props = MainScreenProps<'Settings'>;

export default function SettingsScreen({ navigation }: Props) {
  const { t } = useTranslation(['settings', 'auth', 'history', 'common']);
  const { user, signOut } = useAuth();

  const [currentPwd, setCurrentPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [newPwdConfirm, setNewPwdConfirm] = useState('');
  const [pwdLoading, setPwdLoading] = useState(false);
  const [pwdMsg, setPwdMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const confirmSignOut = () => {
    Alert.alert(t('auth:logout'), t('auth:logoutConfirm'), [
      { text: t('common:cancel'), style: 'cancel' },
      {
        text: t('auth:logout'),
        style: 'destructive',
        onPress: async () => {
          await signOut();
        },
      },
    ]);
  };

  const submitPassword = async () => {
    setPwdMsg(null);
    if (newPwd.length < 8) {
      setPwdMsg({ kind: 'err', text: t('auth:passwordTooShort') });
      return;
    }
    if (newPwd !== newPwdConfirm) {
      setPwdMsg({ kind: 'err', text: t('auth:passwordMismatch') });
      return;
    }
    setPwdLoading(true);
    try {
      await api.auth.changePassword(currentPwd, newPwd);
      setPwdMsg({ kind: 'ok', text: t('settings:passwordChanged') });
      setCurrentPwd('');
      setNewPwd('');
      setNewPwdConfirm('');
    } catch (e) {
      setPwdMsg({ kind: 'err', text: describeError(e, 'passwordChangeFailed') });
    } finally {
      setPwdLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 24}
        style={{ flex: 1 }}
      >
        <ScrollView contentContainerStyle={styles.scroll}>
          {/* Profile card */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{t('settings:profile')}</Text>
            <Text style={styles.profileName}>{user?.full_name || user?.email}</Text>
            {user?.email ? <Text style={styles.profileMeta}>{user.email}</Text> : null}
            {user?.company ? <Text style={styles.profileMeta}>{user.company}</Text> : null}
          </View>

          {/* Language */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{t('settings:language')}</Text>
            <Text style={styles.cardMeta}>{t('settings:languageDescription')}</Text>
            <View style={{ marginTop: spacing.md }}>
              <LanguageSwitcher />
            </View>
          </View>

          {/* Password */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{t('settings:changePassword')}</Text>
            <Field label={t('settings:currentPassword')}>
              <TextInput
                style={styles.input}
                value={currentPwd}
                onChangeText={setCurrentPwd}
                secureTextEntry
                textContentType="password"
                placeholderTextColor={colors.textDim}
              />
            </Field>
            <Field label={t('settings:newPassword')}>
              <TextInput
                style={styles.input}
                value={newPwd}
                onChangeText={setNewPwd}
                secureTextEntry
                textContentType="newPassword"
                placeholderTextColor={colors.textDim}
              />
            </Field>
            <Field label={t('settings:newPasswordConfirm')}>
              <TextInput
                style={styles.input}
                value={newPwdConfirm}
                onChangeText={setNewPwdConfirm}
                secureTextEntry
                textContentType="newPassword"
                placeholderTextColor={colors.textDim}
              />
            </Field>
            {pwdMsg ? (
              <Text
                style={[
                  styles.msg,
                  pwdMsg.kind === 'ok' ? styles.msgOk : styles.msgErr,
                ]}
              >
                {pwdMsg.text}
              </Text>
            ) : null}
            <UploadButton
              label={t('settings:changePassword')}
              loading={pwdLoading}
              onPress={submitPassword}
              style={{ marginTop: spacing.md }}
            />
          </View>

          {/* About */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{t('settings:about')}</Text>
            <SettingRow label={t('settings:version')} value="0.1.0" />
            <Pressable
              accessibilityRole="link"
              onPress={() => navigation.navigate('History')}
              style={styles.rowBtn}
            >
              <Text style={styles.rowBtnText}>{t('history:title')}</Text>
              <Text style={styles.rowBtnArrow}>›</Text>
            </Pressable>
          </View>

          <UploadButton
            label={t('auth:logout')}
            variant="danger"
            onPress={confirmSignOut}
            style={{ marginTop: spacing.lg }}
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

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.settingRow}>
      <Text style={styles.settingLabel}>{label}</Text>
      <Text style={styles.settingValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xxl, paddingBottom: spacing.huge },

  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.lg,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  cardTitle: { ...typography.h3, color: colors.text, marginBottom: spacing.sm },
  cardMeta: { ...typography.caption, color: colors.textMuted },

  profileName: { ...typography.bodyBold, color: colors.text },
  profileMeta: { ...typography.caption, color: colors.textMuted, marginTop: spacing.xxs },

  field: { marginBottom: spacing.md },
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
  msg: { ...typography.caption, marginTop: spacing.xs },
  msgOk: { color: colors.success },
  msgErr: { color: colors.danger },

  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
  },
  settingLabel: { ...typography.body, color: colors.textMuted },
  settingValue: { ...typography.body, color: colors.text },

  rowBtn: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  rowBtnText: { ...typography.body, color: colors.text },
  rowBtnArrow: { color: colors.textMuted, fontSize: 22 },
});
