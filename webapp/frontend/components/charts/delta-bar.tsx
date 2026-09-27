export function DeltaBar({ value, max }: { readonly value: number; readonly max: number }) {
  const safeMax = max || 1;
  const pct = Math.min(100, (Math.abs(value) / safeMax) * 100) / 2;
  const positive = value >= 0;

  return (
    <div
      className="delta-bar"
      role="img"
      aria-label={`${positive ? "Positive" : "Negative"} ${Math.abs(value).toFixed(1)} out of a maximum of ${safeMax}`}
    >
      <div className="delta-bar-track">
        <div className="delta-bar-zero" />
        <div
          className={`delta-bar-fill${positive ? " is-positive" : " is-negative"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`delta-bar-value${positive ? " is-positive" : " is-negative"}`}>
        {positive ? "+" : ""}
        {value.toFixed(1)}
      </span>
    </div>
  );
}
