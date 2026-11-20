import { acknowledge } from '../api';
import type { Alarm } from '../types';

interface AlarmListProps {
  alarms: Alarm[];
  canAck: boolean;
  operator: string;
  onChanged: () => void;
}

export function AlarmList({ alarms, canAck, operator, onChanged }: AlarmListProps): JSX.Element {
  const ack = async (alarm: Alarm): Promise<void> => {
    await acknowledge(alarm.alarm_id, operator);
    onChanged();
  };

  return (
    <section className="card">
      <h2>Alarm list <span className="count">{alarms.length}</span></h2>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Priority</th><th>Segment</th><th>Cause</th><th>State</th><th>Time</th><th /></tr></thead>
          <tbody>
            {alarms.map((alarm) => (
              <tr key={alarm.alarm_id}>
                <td><span className={`pill ${alarm.priority}`}>{alarm.priority}</span></td>
                <td>{alarm.segment}</td>
                <td>{alarm.cause}</td>
                <td>{alarm.state}</td>
                <td>{alarm.created_at.slice(11, 19)}</td>
                <td>
                  {canAck && alarm.state === 'ACTIVE' && (
                    <button className="mini" onClick={() => void ack(alarm)}>Ack</button>
                  )}
                </td>
              </tr>
            ))}
            {alarms.length === 0 && <tr><td colSpan={6} className="empty">No active alarms</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
