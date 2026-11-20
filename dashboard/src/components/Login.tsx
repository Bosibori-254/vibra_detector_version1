import { useState, type FormEvent } from 'react';
import { login } from '../api';

interface LoginProps {
  onSuccess: (role: string) => void;
}

export function Login({ onSuccess }: LoginProps): JSX.Element {
  const [username, setUsername] = useState('operator');
  const [password, setPassword] = useState('operator');
  const [error, setError] = useState('');

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    try {
      const token = await login(username, password);
      const payload = JSON.parse(atob(token.split('.')[1])) as { role: string };
      onSuccess(payload.role);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    }
  };

  return (
    <div className="login-panel">
      <h1>PipeGuard</h1>
      <p>Pipeline vibration control room</p>
      <form onSubmit={(event) => void submit(event)}>
        <label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        <button type="submit">Sign in</button>
      </form>
      {error && <p className="error">{error}</p>}
      <small>Demo roles: viewer, operator, engineer, admin (matching password).</small>
    </div>
  );
}
