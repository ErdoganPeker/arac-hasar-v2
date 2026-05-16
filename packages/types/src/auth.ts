/**
 * Authentication and authorization types shared across web, desktop, and mobile clients.
 */

export type UserRole = 'admin' | 'user';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  created_at: string;
  is_active: boolean;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
}

export interface LoginResponse {
  user: User;
  tokens: AuthTokens;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface RefreshTokenResponse {
  access_token: string;
  refresh_token?: string;
}

export interface AuthSession {
  user: User;
  tokens: AuthTokens;
  expires_at?: string;
}

export const USER_ROLE_TR: Record<UserRole, string> = {
  admin: 'Yönetici',
  user: 'Kullanıcı',
};
