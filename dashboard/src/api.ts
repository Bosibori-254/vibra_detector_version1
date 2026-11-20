import type { ActionAudit, Alarm, Overview } from './types';

const TOKEN_KEY = 'pipeguard-token';

export function getToken(): string | null {
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

export function roleFromToken(token: string): string {
  try {
    const payload = token.split('.')[1];
    const decoded = JSON.parse(atob(payload)) as { role?: string };
    return decoded.role ?? 'viewer';
  } catch {
    return 'viewer';
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(`${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as T;
}

export async function login(username: string, password: string): Promise<string> {
  const result = await request<{ access_token: string }>('/api/auth/token', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  setToken(result.access_token);
  return result.access_token;
}

export const getOverview = (): Promise<Overview> => request<Overview>('/api/overview');
export const getAlarms = (): Promise<Alarm[]> => request<Alarm[]>('/api/alarms');
export const getActions = (): Promise<ActionAudit[]> => request<ActionAudit[]>('/api/actions');

export function acknowledge(alarmId: string, operator: string): Promise<Alarm> {
  return request<Alarm>(`/api/alarms/${encodeURIComponent(alarmId)}/ack`, {
    method: 'POST',
    body: JSON.stringify({ operator }),
  });
}

export function setKillSwitch(active: boolean): Promise<{ kill_switch: boolean }> {
  return request<{ kill_switch: boolean }>('/api/kill-switch', {
    method: 'POST',
    body: JSON.stringify({ active }),
  });
}

export function manualControl(target: string, value: number, reason: string): Promise<ActionAudit> {
  return request<ActionAudit>('/api/manual-control', {
    method: 'POST',
    body: JSON.stringify({ target, value, reason }),
  });
}
