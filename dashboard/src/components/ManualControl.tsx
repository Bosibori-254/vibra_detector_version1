import { useState, type FormEvent } from 'react';
import { manualControl } from '../api';

interface ManualControlProps { currentSpeed: number }

export function ManualControl({ currentSpeed }: ManualControlProps): JSX.Element {
  const [target, setTarget] = useState('vfd_speed_rpm');
  const [value, setValue] = useState(currentSpeed);
  const [reason, setReason] = useState('Operator adjustment');
  const [message, setMessage] = useState('');

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    try {
      const audit = await manualControl(target, Number(value), reason);
      setMessage(`${audit.result}: ${audit.reason || 'command accepted'}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Command failed');
    }
  };

  return (
    <section className="card">
      <h2>Manual control <small>engineer+</small></h2>
      <form className="manual-form" onSubmit={(event) => void submit(event)}>
        <label>Target<select value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="vfd_speed_rpm">VFD speed (rpm)</option>
          <option value="valve_close_rate_pct_s">Valve close rate (%/s)</option>
        </select></label>
        <label>Value<input type="number" value={value} onChange={(e) => setValue(Number(e.target.value))} /></label>
        <label>Reason<input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <button type="submit">Send bounded command</button>
      </form>
      {message && <p className="hint">{message}</p>}
      <small>All commands are bounded, cooldown-limited and audit-logged.</small>
    </section>
  );
}
