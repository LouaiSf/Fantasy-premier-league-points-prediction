export function Sparkline({
  values,
  width = 96,
  height = 28,
  highlightLast = false,
}: {
  readonly values: number[];
  readonly width?: number;
  readonly height?: number;
  readonly highlightLast?: boolean;
}) {
  if (values.length === 0) return null;

  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const pad = 3;
  const stepX = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0;
  const points = values.map((value, index) => {
    const x = pad + index * stepX;
    const y = pad + (1 - (value - min) / range) * (height - pad * 2);
    return { x, y };
  });
  const path = points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const last = points[points.length - 1];

  return (
    <svg
      className="sparkline-svg"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Trend over ${values.length} points: ${values.join(", ")}`}
    >
      <polyline points={path} fill="none" stroke="var(--lime)" strokeWidth={1.5} />
      {highlightLast && last && <circle cx={last.x} cy={last.y} r={2.5} fill="var(--lime)" />}
    </svg>
  );
}
