"use client";

import { useApp } from "@/components/providers/app-provider";
import { crestUrl } from "@/lib/format";

export function CrestTicker() {
  const { snapshot } = useApp();
  const teams = snapshot?.teams ?? [];

  return (
    <div className="ticker" aria-label="Premier League clubs in the local season data">
      <div className="shell ticker-inner">
        <span className="ticker-label">Local season</span>
        {teams.map((team) => (
          <button
            key={team.id}
            type="button"
            className="crest-btn"
            data-team={team.short_name}
            title={team.name}
          >
            <img src={crestUrl(team.code)} alt={team.name} width={24} height={24} loading="lazy" />
          </button>
        ))}
      </div>
    </div>
  );
}
