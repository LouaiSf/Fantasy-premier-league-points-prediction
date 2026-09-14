import type { CSSProperties } from "react";

const CLUB_COLORS: Record<string, [string, string]> = {
  Arsenal: ["#ef0107", "#7a0004"],
  "Aston Villa": ["#95bfe5", "#530c2b"],
  Bournemouth: ["#da291c", "#3a0a06"],
  Brentford: ["#d20000", "#4a0000"],
  Brighton: ["#0057b8", "#001e42"],
  Burnley: ["#6c1d45", "#2b0b1c"],
  Chelsea: ["#034694", "#0a1c42"],
  "Coventry City": ["#6caddf", "#003da5"],
  Coventry: ["#6caddf", "#003da5"],
  "Crystal Palace": ["#1b458f", "#8d1c25"],
  Everton: ["#003399", "#001a4d"],
  Fulham: ["#b3121d", "#141414"],
  "Hull City": ["#f5a623", "#111111"],
  Hull: ["#f5a623", "#111111"],
  "Ipswich Town": ["#0033a0", "#ed1a3b"],
  Ipswich: ["#0033a0", "#ed1a3b"],
  Leeds: ["#ffcd00", "#1d428a"],
  "Leeds United": ["#ffcd00", "#1d428a"],
  Leicester: ["#003090", "#fdbe11"],
  "Leicester City": ["#003090", "#fdbe11"],
  Liverpool: ["#c8102e", "#5a0010"],
  Luton: ["#f78f1e", "#002d62"],
  "Luton Town": ["#f78f1e", "#002d62"],
  "Man City": ["#6cabdd", "#1c2c5b"],
  "Manchester City": ["#6cabdd", "#1c2c5b"],
  "Man Utd": ["#da291c", "#4e0c0c"],
  "Manchester United": ["#da291c", "#4e0c0c"],
  Middlesbrough: ["#e11b22", "#ffffff"],
  Newcastle: ["#3d3d3d", "#0c0c0c"],
  "Newcastle United": ["#3d3d3d", "#0c0c0c"],
  Norwich: ["#00a650", "#fff200"],
  "Norwich City": ["#00a650", "#fff200"],
  "Nott'm Forest": ["#dd0000", "#5c0000"],
  "Nottingham Forest": ["#dd0000", "#5c0000"],
  "Sheffield United": ["#ee2737", "#000000"],
  "Sheffield Utd": ["#ee2737", "#000000"],
  Southampton: ["#d71920", "#ffffff"],
  Spurs: ["#1d2f6f", "#0a1130"],
  Tottenham: ["#1d2f6f", "#0a1130"],
  Sunderland: ["#e21c21", "#0b0b0b"],
  Watford: ["#fbee23", "#ed2127"],
  "West Brom": ["#122f67", "#ffffff"],
  "West Bromwich Albion": ["#122f67", "#ffffff"],
  "West Ham": ["#7a263a", "#2d0e17"],
  "West Ham United": ["#7a263a", "#2d0e17"],
  Wolves: ["#fdb913", "#6e4e00"],
  Wolverhampton: ["#fdb913", "#6e4e00"],
};

export function getClubColors(team: string): [string, string] {
  if (CLUB_COLORS[team]) return CLUB_COLORS[team];
  const cleaned = team.toLowerCase().replace(/[^a-z0-9]/g, "");
  for (const [key, val] of Object.entries(CLUB_COLORS)) {
    if (key.toLowerCase().replace(/[^a-z0-9]/g, "") === cleaned) {
      return val;
    }
  }
  return ["#444", "#111"];
}

export function clubStyle(team: string): CSSProperties {
  const [c1, c2] = getClubColors(team);
  return { "--c1": c1, "--c2": c2 } as CSSProperties;
}

