import { useCallback, useEffect, useMemo, useState } from 'react';
import { clearToken, getOverview, getAlarms, getActions, getToken, roleFromToken, setKillSwitch } from './api';
import { useAlerts } from './useAlerts';
import { Header } from './components/Header';
import { Login } from './components/Login';
import { PipelineMap } from './components/PipelineMap';
import { LiveSignals } from './components/LiveSignals';
import { AlarmList } from './components/AlarmList';
import { ActionLog } from './components/ActionLog';
import { DeviceHealth } from './components/DeviceHealth';
import { ManualControl } from './components/ManualControl';
import type { ActionAudit, Alarm, Overview } from './types';
import './index.css';

export default function App(): JSX.Element {
  const [token, setTokenState] = useState<string | null>(getToken());
  const [overview, setOverview] = useState<Overview | null>(null);
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [actions, setActions] = useState<ActionAudit[]>([]);
  const [selectedSegment, setSelectedSegment] = useState('seg-12');
  const [error, setError] = useState('');
  const events = useAlerts();
  const role = useMemo(() => (token ? roleFromToken(token) : 'viewer'), [token]);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const [o, a, log] = await Promise.all([getOverview(), getAlarms(), getActions()]);
      setOverview(o);
      setAlarms(a);
      setActions(log);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Backend unavailable');
    }
  }, []);

  useEffect(() => {
    if (!token) return;
    void refresh();
  }, [token, refresh]);

  const eventCount = events.length;
  useEffect(() => {
    if (!token || eventCount === 0) return;
    void refresh();
  }, [eventCount, token, refresh]);

  if (!token) {
    return <Login onSuccess={(next) => setTokenState(next)} />;
  }

  const critical = alarms.find((alarm) => alarm.priority === 'critical' && alarm.state === 'ACTIVE');
  const severity = critical ? 1 : alarms.some((a) => a.priority === 'warning') ? 0.6 : 0.05;
  const cause = critical?.cause ?? alarms[0]?.cause ?? 'normal';
  const speed = overview?.devices?.simulated?.vfd_speed_rpm ?? 2950;

  const toggleKill = async (active: boolean): Promise<void> => {
    await setKillSwitch(active);
    await refresh();
  };

  return (
    <div className="app">
      <Header
        site={overview?.site ?? 'gulf-north'}
        role={role}
        killSwitch={overview?.kill_switch ?? false}
        onKillSwitch={(active) => void toggleKill(active)}
        onLogout={() => { clearToken(); setTokenState(null); }}
      />
      {critical && <div className="alarm-banner">CRITICAL: {critical.message}</div>}
      {error && <div className="error-banner">{error}</div>}
      <PipelineMap alarms={alarms} selectedSegment={selectedSegment} onSelect={setSelectedSegment} />
      <LiveSignals severity={severity} cause={cause} />
      <div className="bottom-grid">
        <AlarmList alarms={alarms} canAck={role !== 'viewer'} operator={role} onChanged={() => void refresh()} />
        <ActionLog actions={actions} />
        <DeviceHealth devices={overview?.devices ?? {}} />
        {(role === 'engineer' || role === 'admin') && <ManualControl currentSpeed={speed} />}
      </div>
    </div>
  );
}
