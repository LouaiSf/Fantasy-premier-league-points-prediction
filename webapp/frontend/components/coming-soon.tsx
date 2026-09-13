export function ComingSoon({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <section className="page" style={{ paddingBlock: "var(--space-16)" }}>
      <div className="shell">
        <div className="section-head">
          <div>
            <p className="eyebrow">{eyebrow}</p>
            <h1>{title}</h1>
          </div>
          <p>{description}</p>
        </div>
        <p style={{ color: "var(--muted-light)", maxWidth: "60ch" }}>
          This surface is being rebuilt on the broadcast design system next. It will read from
          the same local player, fixture and prediction data as My Team.
        </p>
      </div>
    </section>
  );
}
