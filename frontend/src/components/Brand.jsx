// The DiffSage mark: a faceted gem split down the middle into a "+" half and
// a "-" half, because the product's whole job is reading diffs.
export function Mark({ className = "mark" }) {
  return (
    <svg className={className} viewBox="0 0 40 40" aria-hidden="true">
      <defs>
        <linearGradient id="gemL" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#a5f5e7" />
          <stop offset="1" stopColor="#14b8a6" />
        </linearGradient>
        <linearGradient id="gemR" x1="1" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#c4b5fd" />
          <stop offset="1" stopColor="#6d28d9" />
        </linearGradient>
      </defs>
      <path d="M20 2 L37 15 L20 38 Z" fill="url(#gemR)" />
      <path d="M20 2 L3 15 L20 38 Z" fill="url(#gemL)" />
      <path d="M3 15 H37 L20 2 Z" fill="#ffffff" opacity="0.18" />
      <path d="M9.5 21h5M12 18.5v5" stroke="#032420" strokeWidth="2" strokeLinecap="round" />
      <path d="M25.5 21h5" stroke="#f5f3ff" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <>
      <Mark />
      <span className="name">
        Diff<b>Sage</b>
      </span>
    </>
  );
}

// fixed, decorative scene behind every screen
export function Backdrop() {
  return (
    <div className="backdrop" aria-hidden="true">
      <div className="floor" />
      <div className="noise" />
    </div>
  );
}
