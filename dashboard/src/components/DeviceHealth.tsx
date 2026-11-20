import type { DeviceInfo } from '../types';

interface DeviceHealthProps { devices: Record<string, DeviceInfo> }

export function DeviceHealth({ devices }: DeviceHealthProps): JSX.Element {
  return (
    <section className="card">
      <h2>Device health</h2>
      <div className="device-grid">
        {Object.entries(devices).map(([name, device]) => (
          <div className="device" key={name}>
            <div className="device-name">{name}</div>
            <div className={device.online ? 'status-online' : 'status-offline'}>
              {device.online ? 'online' : 'offline'}
            </div>
            {typeof device.vfd_speed_rpm === 'number' && <div>{device.vfd_speed_rpm} rpm</div>}
            {typeof device.vibration_index === 'number' && <div>index {device.vibration_index}</div>}
          </div>
        ))}
      </div>
    </section>
  );
}
