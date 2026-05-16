import React from 'react';
import { View, StyleSheet } from 'react-native';
import { NavigationContainer, DarkTheme, Theme } from '@react-navigation/native';

import AuthStack from './AuthStack';
import MainStack from './MainStack';
import { useAuth } from '../services/AuthContext';
import LoadingSpinner from '../components/LoadingSpinner';
import { colors } from '../theme';

const navTheme: Theme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    background: colors.bg,
    card: colors.bg,
    border: colors.divider,
    text: colors.text,
    primary: colors.primary,
    notification: colors.danger,
  },
};

export default function RootNavigator() {
  const { ready, authenticated } = useAuth();

  if (!ready) {
    return (
      <View style={styles.splash}>
        <LoadingSpinner fullscreen />
      </View>
    );
  }

  return (
    <NavigationContainer theme={navTheme}>
      {authenticated ? <MainStack /> : <AuthStack />}
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  splash: { flex: 1, backgroundColor: colors.bg },
});
