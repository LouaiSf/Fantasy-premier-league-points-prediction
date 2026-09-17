import type { ModelSummary } from "@/lib/types";
import { timeAgo } from "@/lib/format";

interface ModelInfoProps {
  model: ModelSummary;
  timestamp: string | null;
}

export function ModelInfo({ model, timestamp }: ModelInfoProps) {
  const positions = Object.entries(model);
  if (positions.length === 0) return null;

  const modelNames = Array.from(new Set(positions.map(([, v]) => v.model))).join(" / ");
  const avgR2 =
    positions.reduce((sum, [, v]) => sum + v.test_r2, 0) / positions.length;

  return (
    <p className="model-info">
      Predictions by <strong>{modelNames}</strong> · test R² {avgR2.toFixed(2)} ·
      updated {timeAgo(timestamp)}
    </p>
  );
}
