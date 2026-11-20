import type { Alarm } from '../types';

interface PipelineMapProps {
  alarms: Alarm[];
  selectedSegment: string;
  onSelect: (segment: string) => void;
}

function statusFor(alarms: Alarm[], segment: string): string {
  const priorities = alarms.filter((a) => a.segment === segment && a.state === 'ACTIVE').map((a) => a.priority);
  if (priorities.includes('critical')) return 'red';
  if (priorities.includes('warning')) return 'yellow';
  if (priorities.length > 0) return 'orange';
  return 'green';
}

export function PipelineMap({ alarms, selectedSegment, onSelect }: PipelineMapProps): JSX.Element {
  const segments = ['seg-10', 'seg-11', 'seg-12', 'seg-13'];
  return (
    <section className="card map-card">
      <h2>Pipeline map</h2>
      <svg viewBox="0 0 640 140" className="pipeline-svg" role="img" aria-label="Pipeline segments">
        <line x1="20" y1="70" x2="620" y2="70" className="pipe" />
        {segments.map((segment, index) => {
          const x = 40 + index * 150;
          const status = statusFor(alarms, segment);
          return (
            <g key={segment} onClick={() => onSelect(segment)} className="segment-group">
              <rect x={x} y="48" width="120" height="44" rx="8" className={`segment ${status} ${selectedSegment === segment ? 'selected' : ''}`} />
              <text x={x + 60} y="76" textAnchor="middle">{segment}</text>
            </g>
          );
        })}
      </svg>
      <div className="legend">
        <span><i className="dot green" />normal</span>
        <span><i className="dot yellow" />warning</span>
        <span><i className="dot red" />critical</span>
      </div>
    </section>
  );
}
