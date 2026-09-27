import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export interface ScatterPoint {
  readonly id: string | number;
  readonly x: number;
  readonly y: number;
  readonly label: string;
  readonly highlight?: boolean;
}

export function Scatter({
  points,
  xLabel,
  yLabel,
  diagonal = false,
  width = 640,
  height = 420,
}: {
  readonly points: ScatterPoint[];
  readonly xLabel: string;
  readonly yLabel: string;
  readonly diagonal?: boolean;
  readonly width?: number;
  readonly height?: number;
}) {
  const pad = { top: 16, right: 16, bottom: 36, left: 44 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  let xMin = Math.min(0, ...xs);
  let xMax = Math.max(1, ...xs);
  let yMin = Math.min(0, ...ys);
  let yMax = Math.max(1, ...ys);
  if (diagonal) {
    xMin = yMin = Math.min(xMin, yMin);
    xMax = yMax = Math.max(xMax, yMax);
  }
  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;

  const scaleX = (value: number) => pad.left + ((value - xMin) / xRange) * plotW;
  const scaleY = (value: number) => pad.top + (1 - (value - yMin) / yRange) * plotH;
  const zeroX = scaleX(0);
  const zeroY = scaleY(0);

  return (
    <svg
      className="scatter-svg"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Scatter plot of ${points.length} players: ${xLabel} versus ${yLabel}`}
    >
      {zeroY >= pad.top && zeroY <= height - pad.bottom && (
        <line x1={pad.left} y1={zeroY} x2={width - pad.right} y2={zeroY} className="scatter-zero" />
      )}
      {zeroX >= pad.left && zeroX <= width - pad.right && (
        <line x1={zeroX} y1={pad.top} x2={zeroX} y2={height - pad.bottom} className="scatter-zero" />
      )}
      {diagonal && (
        <line
          x1={scaleX(xMin)}
          y1={scaleY(xMin)}
          x2={scaleX(xMax)}
          y2={scaleY(xMax)}
          className="scatter-diagonal"
        />
      )}
      <text x={pad.left + plotW / 2} y={height - 8} textAnchor="middle" className="scatter-axis-label">
        {xLabel}
      </text>
      <text
        x={12}
        y={pad.top + plotH / 2}
        textAnchor="middle"
        className="scatter-axis-label"
        transform={`rotate(-90 12 ${pad.top + plotH / 2})`}
      >
        {yLabel}
      </text>
      {points.map((point) => (
        <Tooltip key={point.id}>
          <TooltipTrigger
            render={
              <circle
                cx={scaleX(point.x)}
                cy={scaleY(point.y)}
                r={point.highlight ? 8 : 4}
                className={`scatter-dot${point.highlight ? " is-highlight" : ""}`}
                tabIndex={0}
                aria-label={`${point.label}: ${xLabel} ${point.x}, ${yLabel} ${point.y}`}
              />
            }
          />
          <TooltipContent>
            {point.label} · {xLabel} {point.x} · {yLabel} {point.y}
          </TooltipContent>
        </Tooltip>
      ))}
    </svg>
  );
}
