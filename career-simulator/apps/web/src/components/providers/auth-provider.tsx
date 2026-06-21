'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import type { UserPublic } from '@career-sim/shared';
import { fetchMe, loginUser, registerUser, type ApiClientError } from '@/lib/api-client';
import { clearStoredToken, getStoredToken, setStoredToken } from '@/lib/auth-storage';

type AuthContextValue = {
  user: UserPublic | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (fullName: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    const token = getStoredToken();
    if (!token) {
      setUser(null);
      return;
    }
    try {
      const { user: me } = await fetchMe();
      setUser(me);
    } catch {
      clearStoredToken();
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refreshUser().finally(() => setLoading(false));
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const { token, user: loggedIn } = await loginUser({ email, password });
    setStoredToken(token);
    setUser(loggedIn);
  }, []);

  const register = useCallback(async (fullName: string, email: string, password: string) => {
    const { token, user: created } = await registerUser({ fullName, email, password });
    setStoredToken(token);
    setUser(created);
  }, []);

  const logout = useCallback(() => {
    clearStoredToken();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout, refreshUser }),
    [user, loading, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export function getAuthErrorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'error' in err) {
    return String((err as ApiClientError).error);
  }
  return 'Something went wrong. Please try again.';
}
