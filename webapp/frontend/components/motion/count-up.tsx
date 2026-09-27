"use client";

import { useCountUp } from "@/lib/use-count-up";

export function CountUp({
  value,
  decimals = 0,
  prefix = "",
  suffix = "",
}: {
  readonly value: number;
  readonly decimals?: number;
  readonly prefix?: string;
  readonly suffix?: string;
}) {
  const animated = useCountUp(value);
  return (
    <span className="data" aria-label={`${prefix}${value.toFixed(decimals)}${suffix}`}>
      {prefix}
      {animated.toFixed(decimals)}
      {suffix}
    </span>
  );
}
