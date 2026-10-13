import React, { createContext, useContext, useEffect, useState } from 'react';
import { api, getToken, setToken } from '../api';

interface AuthCtx { user: any | null; ready: boolean; login: (t: string) => Promise<void>; logout: () => void; refresh: () => Promise<void> }
const Ctx = createContext<AuthCtx>({ user: null, ready: false, login: async () => {}, logout: () => {}, refresh: async () => {} });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<any | null>(null);
  const [ready, setReady] = useState(false);

  const load = async () => {
    if (!getToken()) { setUser(null); setReady(true); return; }
    try { setUser(await api.me()); } catch { setToken(''); setUser(null); }
    setReady(true);
  };
  useEffect(() => { load(); }, []);

  const login = async (t: string) => { setToken(t); await load(); };
  const logout = () => { setToken(''); setUser(null); };
  return <Ctx.Provider value={{ user, ready, login, logout, refresh: load }}>{children}</Ctx.Provider>;
}
export const useAuth = () => useContext(Ctx);
