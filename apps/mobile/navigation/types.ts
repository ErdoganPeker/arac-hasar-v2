import type { NativeStackScreenProps } from '@react-navigation/native-stack';

export type AuthStackParamList = {
  Login: undefined;
  Register: undefined;
  ForgotPassword: undefined;
};

export type MainStackParamList = {
  Home: undefined;
  Camera: { mode?: 'sync' | 'async' } | undefined;
  Upload: { mode?: 'sync' | 'async'; photos?: string[] } | undefined;
  Result: { inspectionId: string; resultPreview?: unknown } | { inspectionId: string };
  History: undefined;
  InspectionDetail: { inspectionId: string };
  Settings: undefined;
};

export type AuthScreenProps<T extends keyof AuthStackParamList> =
  NativeStackScreenProps<AuthStackParamList, T>;

export type MainScreenProps<T extends keyof MainStackParamList> =
  NativeStackScreenProps<MainStackParamList, T>;
