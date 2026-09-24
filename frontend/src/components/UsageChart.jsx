// Requests per day as isometric 3D bars, drawn in plain SVG: each bar is a
// front face, a side face and a top face. Today's bar is violet. Not worth a
// charting library for one chart.
const W = 34; // bar width
const D = 12; // depth offset for the side/top faces
const GAP = 26;
const H = 170; // plot height
const PAD = 30; // room for labels below

export default function UsageChart({ days }) {
  if (!days?.length) return null;
  const max = Math.max(1, ...days.map((d) => d.requests));
  const width = days.length * (W + GAP) + D + 8;
  const ticks = [...new Set([0, 0.5, 1].map((f) => Math.round(max * f)))]; // max=1 would give 0,1,1
  const total = days.reduce((n, d) => n + d.requests, 0);

  return (
    <figure className="chart">
      <svg viewBox={`-34 -${D + 6} ${width + 34} ${H + PAD + D + 6}`} role="img"
        aria-label={`Requests per day over the last ${days.length} days: ${total} in total, peak ${max} in one day`}>
        <defs>
          <linearGradient id="barFront" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#5eead4" />
            <stop offset="1" stopColor="#0d9488" />
          </linearGradient>
          <linearGradient id="barFrontToday" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#c4b5fd" />
            <stop offset="1" stopColor="#7c3aed" />
          </linearGradient>
        </defs>
        {ticks.map((t) => {
          const y = H - (t / max) * (H - 10);
          return (
            <g key={t}>
              <line className="grid-line" x1="0" x2={width} y1={y} y2={y} strokeDasharray="3 5" />
              <text x="-8" y={y + 3} textAnchor="end">{t}</text>
            </g>
          );
        })}
        {days.map((d, i) => {
          const bh = d.requests ? Math.max(4, (d.requests / max) * (H - 10)) : 0;
          const x = i * (W + GAP) + 4;
          const y = H - bh;
          const today = i === days.length - 1;
          const date = new Date(d.date + "T00:00:00");
          return (
            <g key={d.date} className={`bar-g ${today ? "today" : ""}`}>
              <title>{`${d.date}: ${d.requests} requests, ${d.tokens} tokens`}</title>
              {bh > 0 ? (
                <>
                  <polygon className="face-side" points={`${x + W},${y} ${x + W + D},${y - D} ${x + W + D},${H - D} ${x + W},${H}`} />
                  <polygon className="face-top" points={`${x},${y} ${x + D},${y - D} ${x + W + D},${y - D} ${x + W},${y}`} />
                  <rect className="face-front" x={x} y={y} width={W} height={bh} />
                </>
              ) : (
                <rect className="zero" x={x} y={H - 2} width={W} height="2" />
              )}
              {(i % 2 === (days.length - 1) % 2) && (
                <text x={x + W / 2} y={H + 22} textAnchor="middle">{date.getDate()}</text>
              )}
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
