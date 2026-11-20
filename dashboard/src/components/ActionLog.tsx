import type { ActionAudit } from '../types';

interface ActionLogProps { actions: ActionAudit[] }

export function ActionLog({ actions }: ActionLogProps): JSX.Element {
  return (
    <section className="card">
      <h2>Action log <span className="count">{actions.length}</span></h2>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Time</th><th>Cause</th><th>Target</th><th>Before → After</th><th>Result</th><th>Operator</th></tr></thead>
          <tbody>
            {actions.map((action) => (
              <tr key={action.action_id}>
                <td>{action.timestamp.slice(11, 19)}</td>
                <td>{action.action_type}</td>
                <td>{action.target || '—'}</td>
                <td>{action.before ?? '—'} → {action.after ?? '—'}</td>
                <td><span className={`pill ${action.result}`}>{action.result}</span></td>
                <td>{action.operator}</td>
              </tr>
            ))}
            {actions.length === 0 && <tr><td colSpan={6} className="empty">No actions recorded</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
