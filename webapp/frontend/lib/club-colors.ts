import type { CSSProperties } from "react";

// Two-stop club gradient pairs (DESIGN.md's --c1/--c2), keyed by the full
// club name as it appears in players_raw.csv / teams.csv. Not every club in
// every season is guaranteed to be listed; clubStyle() falls back to a
// neutral grey pair rather than throwing.
const CLUB_COLORS: Record<string, [string, string]> = {
  Arsenal: ["#ef0107", "#7a0004"],
  "Aston Villa": ["#95bfe5", "#530c2b"],
  Bournemouth: ["#da291c", "#3a0a06"],
  Brentford: ["#d20000", "#4a0000"],
  "Brighton and Hove Albion": ["#0057b8", "#001e42"],
  Burnley: ["#6c1d45", "#2b0b1c"],
  Chelsea: ["#034694", "#0a1c42"],
  "Crystal Palace": ["#1b458f", "#8d1c25"],
  Everton: ["#003399", "#001a4d"],
  Fulham: ["#b3121d", "#141414"],
  "Ipswich Town": ["#0044a9", "#00285f"],
  "Leeds United": ["#ffcd00", "#1d428a"],
  "Leicester City": ["#003090", "#001a4f"],
  Liverpool: ["#c8102e", "#5a0010"],
  "Manchester City": ["#6cabdd", "#1c2c5b"],
  "Manchester United": ["#da291c", "#4e0c0c"],
  "Newcastle United": ["#3d3d3d", "#0c0c0c"],
  "Nottingham Forest": ["#dd0000", "#5c0000"],
  Southampton: ["#d71920", "#160b0c"],
  Sunderland: ["#e21c21", "#0b0b0b"],
  "Tottenham Hotspur": ["#1d2f6f", "#0a1130"],
  "West Ham United": ["#7a263a", "#2d0e17"],
  "Wolverhampton Wanderers": ["#fdb913", "#6e4e00"],
};

export function clubStyle(team: string): CSSProperties {
  const [c1, c2] = CLUB_COLORS[team] ?? ["#555", "#111"];
  return { "--c1": c1, "--c2": c2 } as CSSProperties;
}
