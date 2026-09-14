import type { CSSProperties } from "react";

const CLUB_COLORS: Record<string, [string, string]> = {
  Arsenal: ["#ef0107", "#7a0004"],
  "Aston Villa": ["#95bfe5", "#530c2b"],
  Bournemouth: ["#da291c", "#3a0a06"],
  Brentford: ["#d20000", "#4a0000"],
  Brighton: ["#0057b8", "#001e42"],
  Burnley: ["#6c1d45", "#2b0b1c"],
  Chelsea: ["#034694", "#0a1c42"],
  "Crystal Palace": ["#1b458f", "#8d1c25"],
  Everton: ["#003399", "#001a4d"],
  Fulham: ["#b3121d", "#141414"],
  Leeds: ["#ffcd00", "#1d428a"],
  Liverpool: ["#c8102e", "#5a0010"],
  "Man City": ["#6cabdd", "#1c2c5b"],
  "Man Utd": ["#da291c", "#4e0c0c"],
  Newcastle: ["#3d3d3d", "#0c0c0c"],
  "Nott'm Forest": ["#dd0000", "#5c0000"],
  Sunderland: ["#e21c21", "#0b0b0b"],
  Spurs: ["#1d2f6f", "#0a1130"],
  "West Ham": ["#7a263a", "#2d0e17"],
  Wolves: ["#fdb913", "#6e4e00"],
};

export function clubStyle(team: string): CSSProperties {
  const [c1, c2] = CLUB_COLORS[team] ?? ["#555", "#111"];
  return { "--c1": c1, "--c2": c2 } as CSSProperties;
}
