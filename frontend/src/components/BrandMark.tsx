export function BrandMark({ className = "" }: { className?: string }) {
  return (
    <div
      className={`relative grid h-12 w-12 shrink-0 place-items-center rounded-[15px] bg-grass ${className}`}
      aria-label="Hi Tuto mascot logo"
    >
      {/* App-icon face: cream outlined squircle with calm eyes */}
      <svg viewBox="0 0 48 48" className="h-9 w-9" fill="none" aria-hidden="true">
        <rect x="8" y="9" width="32" height="30" rx="10" stroke="#FDF1E7" strokeWidth="4" />
        <rect x="19" y="19" width="3.6" height="10" rx="1.8" fill="#FDF1E7" />
        <rect x="26" y="19" width="3.6" height="10" rx="1.8" fill="#FDF1E7" />
      </svg>
    </div>
  );
}
