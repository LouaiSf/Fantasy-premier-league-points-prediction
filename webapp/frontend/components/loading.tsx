export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading-state">
      <div className="loading-spinner" />
      <p className="loading-label">{label}</p>
    </div>
  );
}
