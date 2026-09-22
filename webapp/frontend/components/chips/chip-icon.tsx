import type { ChipId } from "@/lib/types";

const CHIP_LABELS: Record<ChipId, string> = {
  triple_captain: "Triple Captain",
  bench_boost: "Bench Boost",
  free_hit: "Free Hit",
  wildcard: "Wildcard",
};

const CHIP_ICON_FILES: Record<ChipId, string> = {
  triple_captain: "3xc",
  bench_boost: "bboost",
  free_hit: "freehit",
  wildcard: "wildcard",
};

interface ChipIconProps {
  id: ChipId;
  size?: "compact" | "large";
}

export function ChipIcon({ id, size = "compact" }: ChipIconProps) {
  return (
    <img
      className={`chip-icon chip-icon--${size}`}
      src={`/icons/chips/${CHIP_ICON_FILES[id]}.png`}
      alt=""
      aria-hidden="true"
      width={size === "large" ? 72 : 42}
      height={size === "large" ? 72 : 42}
      title={CHIP_LABELS[id]}
    />
  );
}
