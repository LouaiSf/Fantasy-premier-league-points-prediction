import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export interface BarStripItem {
  readonly key: string;
  readonly label: string;
  readonly value: number | null;
  readonly state?: "now" | "best" | "default";
}

function barColor(item: BarStripItem): string {
  if (item.value != null && item.value < 0) return "var(--pink)";
  if (item.state === "now") return "var(--lime)";
  if (item.state === "best") return "var(--white)";
  return "rgba(255,255,255,.28)";
}

// Past this many bars, a persistent label under every column overlaps its
// neighbours and reads as noise -- the exact value is still available via
// the tooltip, so labels are dropped rather than shrunk into garbage.
const MAX_LABELLED_ITEMS = 10;

export function BarStrip({ items, height = 44 }: { readonly items: BarStripItem[]; readonly height?: number }) {
  const values = items.map((item) => item.value).filter((value): value is number => value != null);
  const maxAbs = Math.max(...values.map((value) => Math.abs(value)), 1);
  const hasNegative = values.some((value) => value < 0);
  const zeroY = hasNegative ? height / 2 : height;
  const barMax = hasNegative ? height / 2 : height;
  const barWidth = `calc((100% - ${(items.length - 1) * 2}px) / ${items.length})`;
  const showLabels = items.length <= MAX_LABELLED_ITEMS;

  return (
    <div
      className="bar-strip"
      role="img"
      aria-label={`Bar chart: ${items.map((item) => `${item.label} ${item.value ?? "no data"}`).join(", ")}`}
      style={{ height }}
    >
      <div className="bar-strip-zero" style={{ bottom: hasNegative ? "50%" : 0 }} />
      {items.map((item) => {
        const barHeight = item.value == null ? 0 : Math.max(2, (Math.abs(item.value) / maxAbs) * barMax);
        const grow = item.value != null && item.value < 0 ? "down" : "up";
        return (
          <Tooltip key={item.key}>
            <TooltipTrigger
              render={
                <div
                  className="bar-strip-col"
                  style={{ width: barWidth }}
                  tabIndex={0}
                  aria-label={`${item.label}: ${item.value == null ? "no data" : item.value}`}
                >
                  {item.value == null ? (
                    <div className="bar-strip-bar hatch" style={{ height: 10, bottom: zeroY - 5, opacity: 0.3 }} />
                  ) : (
                    <div
                      className="bar-strip-bar"
                      style={{
                        height: barHeight,
                        bottom: grow === "up" ? zeroY : zeroY - barHeight,
                        background: barColor(item),
                      }}
                    />
                  )}
                  {showLabels && <span className="bar-strip-label">{item.label}</span>}
                </div>
              }
            />
            <TooltipContent>
              {item.label}: {item.value == null ? "no data" : item.value}
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
}
