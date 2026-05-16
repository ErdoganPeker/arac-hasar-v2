/**
 * App.tsx — Root component for the Hasarİ mobile app.
 *
 * Stack:
 *   - Expo SDK 52 / React Native 0.76 / TypeScript
 *   - React Navigation v7 (native stack)
 *   - i18next (TR primary, EN secondary)
 *   - expo-secure-store auth token persistence
 *   - SafeAreaProvider for bottom-safe navigation on iOS / Android
 */
import 'react-native-gesture-handler';
import React, { useEffect, useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { I18nextProvider } from 'react-i18next';

import i18n, { initI18n } from './i18n';
import { AuthProvider } from './services/AuthContext';
import RootNavigator from './navigation/RootNavigator';
import LoadingSpinner from './components/LoadingSpinner';
import { colors } from './theme';

export default function App() {
  const [i18nReady, setI18nReady] = useState(false);

  useEffect(() => {
    initI18n().finally(() => setI18nReady(true));
  }, []);

  if (!i18nReady) {
    return <LoadingSpinner fullscreen />;
  }

  return (
    <SafeAreaProvider>
      <I18nextProvider i18n={i18n}>
        <AuthProvider>
          <StatusBar style="light" backgroundColor={colors.bg} />
          <RootNavigator />
        </AuthProvider>
      </I18nextProvider>
    </SafeAreaProvider>
  );
}
