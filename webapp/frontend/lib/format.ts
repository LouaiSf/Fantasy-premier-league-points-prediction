function hasNumericValue(value: unknown): value is number | string {
  return (
    value !== null &&
    value !== undefined &&
    value !== "" &&
    Number.isFinite(Number(value))
  );
}

export function money(value: unknown): string {
  if (!hasNumericValue(value)) return "--";
  const n = Number(value);
  return `${n < 0 ? "-" : ""}£${Math.abs(n).toFixed(1)}m`;
}

export function num(value: unknown, digits = 1): string {
  return hasNumericValue(value) ? Number(value).toFixed(digits) : "--";
}

export function signed(value: unknown, digits = 1): string {
  if (!hasNumericValue(value)) return "--";
  const n = Number(value);
  const sign = n > 0 ? "+" : n < 0 ? "−" : "";
  return `${sign}${Math.abs(n).toFixed(digits)}`;
}

export function crestUrl(code: number, size = 100): string {
  return `https://resources.premierleague.com/premierleague/badges/${size}/t${code}.png`;
}
