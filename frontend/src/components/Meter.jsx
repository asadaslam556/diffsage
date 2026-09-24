import { compact } from "../lib/format.js";

// used / limit as a glowing bar. A null limit means unlimited. `bare` drops
// the heading row for when the card around it already shows the numbers.
export default function Meter({ label, used, limit, hint, bare = false }) {
  const unlimited = limit == null;
  const pct = unlimited ? 0 : Math.min(100, (used / Math.max(limit, 1)) * 100);
  let tone = "ok";
  if (pct >= 100) tone = "full";
  else if (pct >= 80) tone = "high";
  return (
    <div className={`meter tone-${tone}`}>
      {!bare && (
        <div className="meter-head">
          <span>{label}</span>
          <span className="meter-num">
            {compact(used)} <span className="of">/ {unlimited ? "unlimited" : compact(limit)}</span>
          </span>
        </div>
      )}
      <div className="track" role="progressbar" aria-valuemin={0} aria-valuemax={unlimited ? undefined : limit}
        aria-valuenow={used} aria-label={label}>
        {!unlimited && <div className="fill" style={{ width: `${pct}%` }} />}
      </div>
      {hint && <p className="meter-hint">{hint}</p>}
    </div>
  );
}
