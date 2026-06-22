'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useAuth as useClerkAuth, useUser } from '@clerk/nextjs';
import type { UserPublic } from '@career-sim/shared';
import { fetchMe, loginUser, registerUser, type ApiClientError } from '@/lib/api-client';
import { setAuthTokenGetter } from '@/lib/auth-token';
import { clearStoredToken, getStoredToken, setStoredToken } from '@/lib/auth-storage';
import { isClerkEnabled } from '@/lib/clerk-config';

type AuthContextValue = {
  user: UserPublic | null;
  loading: boolean;
  clerkEnabled: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (fullName: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function LegacyAuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setAuthTokenGetter(async () => getStoredToken());
  }, []);

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
    () => ({
      user,
      loading,
      clerkEnabled: false,
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, loading, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function ClerkAuthProvider({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn, user: clerkUser } = useUser();
  const { getToken, signOut } = useClerkAuth();
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setAuthTokenGetter(async () => {
      if (!isSignedIn) return null;
      return getToken();
    });
  }, [getToken, isSignedIn]);

  const refreshUser = useCallback(async () => {
    if (!isSignedIn) {
      setUser(null);
      return;
    }
    try {
      const { user: me } = await fetchMe();
      setUser(me);
    } catch {
      setUser(null);
    }
  }, [isSignedIn]);

  useEffect(() => {
    if (!isLoaded) return;
    refreshUser().finally(() => setLoading(false));
  }, [isLoaded, isSignedIn, clerkUser?.id, refreshUser]);

  const login = useCallback(async () => {
    throw new Error('Use Clerk sign-in');
  }, []);

  const register = useCallback(async () => {
    throw new Error('Use Clerk sign-up');
  }, []);

  const logout = useCallback(() => {
    void signOut();
    setUser(null);
  }, [signOut]);

  const value = useMemo(
    () => ({
      user,
      loading: !isLoaded || loading,
      clerkEnabled: true,
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, isLoaded, loading, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  if (isClerkEnabled()) {
    return <ClerkAuthProvider>{children}</ClerkAuthProvider>;
  }
  return <LegacyAuthProvider>{children}</LegacyAuthProvider>;
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
