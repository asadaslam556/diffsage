// The DiffSage mark: a crystal split down the middle into a "-" half and a
// "+" half, because the product's whole job is reading diffs.
export function Mark({ className = "mark" }) {
  return (
    <svg className={className} viewBox="0 0 40 40" aria-hidden="true">
      <path d="M20 1 7 11l13-2Z" fill="#7fe0cd" />
      <path d="M7 11l13-2v22L7 29Z" fill="#4cc3ad" />
      <path d="M7 29l13 2v8Z" fill="#37a592" />
      <path d="M20 1l13 10-13-2Z" fill="#d2fbf3" />
      <path d="M33 11 20 9v22l13-2Z" fill="#a5f5e7" />
      <path d="M33 29 20 31v8Z" fill="#7fe0cd" />
      <path d="M20 1v38" stroke="#070b12" strokeOpacity="0.45" strokeWidth="0.8" />
      <path d="M10.5 20h6M26.5 17v6M23.5 20h6" stroke="#0a2724" strokeWidth="2.2" strokeLinecap="round" />
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
