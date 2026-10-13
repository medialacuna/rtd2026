const TOKEN_KEY = 'rtd-token';

export function getToken(): string { return localStorage.getItem(TOKEN_KEY) || ''; }
export function setToken(t: string) { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); }

async function req(path: string, opts: RequestInit = {}) {
  const headers: Record<string, string> = { ...(opts.headers as any) || {} };
  if (!(opts.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const tok = getToken();
  if (tok) headers['x-session-token'] = tok;
  const r = await fetch(path, { ...opts, headers });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
  return data;
}

export const api = {
  health: () => req('/api/health'),
  steps: () => req('/api/auth/steps'),
  requestLink: (email: string) => req('/api/auth/request-link', { method: 'POST', body: JSON.stringify({ email }) }),
  verify: (token: string) => req('/api/auth/verify', { method: 'POST', body: JSON.stringify({ token }) }),
  me: () => req('/api/auth/me'),
  patchMe: (p: any) => req('/api/auth/me', { method: 'PATCH', body: JSON.stringify(p) }),
  replicas: (sort = 'fresh') => req(`/api/replicas?sort=${sort}&limit=60`),
  createReplica: (text: string, is_tost = false) => req('/api/replicas', { method: 'POST', body: JSON.stringify({ text, is_tost }) }),
  retract: (id: number) => req(`/api/replicas/${id}`, { method: 'DELETE' }),
  scenes: () => req('/api/scenes?limit=50'),
  sceneOfDay: () => req('/api/scenes/day'),
  muarMap: () => req('/api/scenes/muar/map'),
  acts: () => req('/api/acts'),
  act: (id: number) => req(`/api/acts/${id}`),
  plays: () => req('/api/plays'),
  play: (id: number) => req(`/api/plays/${id}`),
  aiAsk: (q: string, section?: string) => req(`/api/ai/ask?question=${encodeURIComponent(q)}${section ? `&section=${section}` : ''}`),
  aiMemory: () => req('/api/ai/memory?limit=80'),
  stageState: () => req('/api/stage/state'),
  stageStart: (session_key: string) => req('/api/stage/session/start', { method: 'POST', body: JSON.stringify({ session_key }) }),
  stageNext: () => req('/api/stage/next', { method: 'POST' }),
  stageAsk: (prompt: string, section?: string) => req('/api/stage/ask', { method: 'POST', body: JSON.stringify({ prompt, section }) }),
};
