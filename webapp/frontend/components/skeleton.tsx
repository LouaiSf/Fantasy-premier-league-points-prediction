export function Skeleton({
  variant,
  count = 1,
}: {
  readonly variant: "row" | "card" | "pitch" | "table" | "hero";
  readonly count?: number;
}) {
  return (
    <div className={`skel-group skel-group--${variant}`} aria-busy="true">
      <span className="sr-only">Loading</span>
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className={`skel skel-${variant}`} aria-hidden="true" />
      ))}
    </div>
  );
}
