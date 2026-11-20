import { useEffect, useState } from 'react';
import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

interface WavePoint { t: number; z: number; envelope: number }
interface BandPoint { band: string; amplitude: number }

const BANDS = ['10', '50', '150', '500', '1k', '2k'];

function makeWave(start: number, severity: number): WavePoint[] {
  const points: WavePoint[] = [];
  for (let i = 0; i < 64; i += 1) {
    const t = start + i * 0.008;
    const amplitude = 0.4 + severity * 0.8;
    points.push({
      t: Number(t.toFixed(3)),
      z: Number((Math.sin(2 * Math.PI * 49 * t) * amplitude + (Math.random() - 0.5) * 0.15).toFixed(3)),
      envelope: Number((amplitude * (0.8 + 0.2 * Math.sin(2 * Math.PI * 3 * t))).toFixed(3)),
    });
  }
  return points;
}

interface LiveSignalsProps { severity: number; cause: string }

export function LiveSignals({ severity, cause }: LiveSignalsProps): JSX.Element {
  const [wave, setWave] = useState<WavePoint[]>(() => makeWave(0, severity));
  const [bands, setBands] = useState<BandPoint[]>(() => BANDS.map((band, i) => ({ band, amplitude: 0.2 + i * 0.04 })));

  useEffect(() => {
    const timer = window.setInterval(() => {
      setWave((previous) => makeWave(previous[previous.length - 1].t + 0.5, severity));
      setBands(BANDS.map((band, i) => ({
        band,
        amplitude: Number((0.2 + i * 0.03 + severity * (i > 2 ? 0.5 : 0.15) + Math.random() * 0.08).toFixed(3)),
      })));
    }, 400);
    return () => window.clearInterval(timer);
  }, [severity]);

  const cells = Array.from({ length: 96 }, (_, i) => {
    const intensity = Math.min(1, 0.15 + severity * 0.5 + Math.random() * 0.35 + (i % 12 === 5 ? 0.25 : 0));
    return intensity;
  });

  return (
    <section className="card signal-card">
      <h2>Live waveform &amp; spectrum <small>{cause}</small></h2>
      <div className="signal-grid">
        <div>
          <h3>Acceleration Z (m/s²)</h3>
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={wave}>
              <XAxis dataKey="t" tick={{ fontSize: 10 }} minTickGap={30} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Line type="monotone" dataKey="z" stroke="#38bdf8" dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="envelope" stroke="#f59e0b" dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div>
          <h3>FFT bands (Hz)</h3>
          <ResponsiveContainer width="100%" height={150}>
            <BarChart data={bands}>
              <XAxis dataKey="band" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Bar dataKey="amplitude" fill="#22d3ee" isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <h3>Spectrogram</h3>
      <div className="spectrogram">
        {cells.map((intensity, index) => (
          <i key={index} style={{ opacity: intensity }} />
        ))}
      </div>
    </section>
  );
}
