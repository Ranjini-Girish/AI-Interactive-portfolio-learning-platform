import { getStoredToken } from './auth-storage';

type TokenGetter = () => Promise<string | null>;

let tokenGetter: TokenGetter | null = null;

/** Clerk mode registers getToken(); legacy mode uses localStorage JWT. */
export function setAuthTokenGetter(getter: TokenGetter): void {
  tokenGetter = getter;
}

export async function getAuthToken(): Promise<string | null> {
  if (tokenGetter) {
    return tokenGetter();
  }
  return getStoredToken();
}
