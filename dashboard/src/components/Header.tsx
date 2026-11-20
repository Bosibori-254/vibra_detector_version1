interface HeaderProps {
  site: string;
  role: string;
  killSwitch: boolean;
  onKillSwitch: (active: boolean) => void;
  onLogout: () => void;
}

export function Header({ site, role, killSwitch, onKillSwitch, onLogout }: HeaderProps): JSX.Element {
  return (
    <header className="topbar">
      <div>
        <span className="brand">PipeGuard</span>
        <span className="site"> {site} · control room</span>
      </div>
      <div className="topbar-actions">
        <span className={`role role-${role}`}>{role}</span>
        {role === 'admin' && (
          <button className={killSwitch ? 'danger active' : 'danger'} onClick={() => onKillSwitch(!killSwitch)}>
            {killSwitch ? 'Resume automation' : 'Kill automation'}
          </button>
        )}
        <button onClick={onLogout}>Sign out</button>
      </div>
    </header>
  );
}
