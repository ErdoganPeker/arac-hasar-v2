import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useTranslation } from 'react-i18next';

import HomeScreen from '../screens/HomeScreen';
import CameraScreen from '../screens/CameraScreen';
import UploadScreen from '../screens/UploadScreen';
import ResultScreen from '../screens/ResultScreen';
import HistoryScreen from '../screens/HistoryScreen';
import InspectionDetailScreen from '../screens/InspectionDetailScreen';
import SettingsScreen from '../screens/SettingsScreen';
import { MainStackParamList } from './types';
import { colors } from '../theme';

const Stack = createNativeStackNavigator<MainStackParamList>();

export default function MainStack() {
  const { t } = useTranslation(['dashboard', 'inspect', 'history', 'settings']);
  return (
    <Stack.Navigator
      initialRouteName="Home"
      screenOptions={{
        headerStyle: { backgroundColor: colors.bg },
        headerTintColor: colors.text,
        headerTitleStyle: { fontWeight: '600' },
        contentStyle: { backgroundColor: colors.bg },
        headerShadowVisible: false,
      }}
    >
      <Stack.Screen
        name="Home"
        component={HomeScreen}
        options={{ headerShown: false }}
      />
      <Stack.Screen
        name="Camera"
        component={CameraScreen}
        options={{ title: t('inspect:cameraTitle'), headerShown: false }}
      />
      <Stack.Screen
        name="Upload"
        component={UploadScreen}
        options={{ title: t('inspect:reviewTitle') }}
      />
      <Stack.Screen
        name="Result"
        component={ResultScreen}
        options={{ title: t('inspect:resultTitle') }}
      />
      <Stack.Screen
        name="History"
        component={HistoryScreen}
        options={{ title: t('history:title') }}
      />
      <Stack.Screen
        name="InspectionDetail"
        component={InspectionDetailScreen}
        options={{ title: t('history:detailTitle') }}
      />
      <Stack.Screen
        name="Settings"
        component={SettingsScreen}
        options={{ title: t('settings:title') }}
      />
    </Stack.Navigator>
  );
}
