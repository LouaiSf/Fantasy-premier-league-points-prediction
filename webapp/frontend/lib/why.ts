import type { FixtureRecord, PlatformSnapshot, PlayerRecord, TeamRecord } from "./types";

export function isFlagged(player: PlayerRecord): boolean {
  return player.status !== "a" || (player.chance_of_playing_next_round ?? 100) < 100;
}

export function teamOf(snapshot: PlatformSnapshot | null, player: Pick<PlayerRecord, "team">): TeamRecord | undefined {
  return snapshot?.teams.find((team) => team.name === player.team);
}

export function nextFixtureFor(snapshot: PlatformSnapshot | null, player: Pick<PlayerRecord, "team">): FixtureRecord | null {
  if (!snapshot || snapshot.gameweek == null) return null;
  return teamOf(snapshot, player)?.fixtures.find((fixture) => fixture.gameweek === snapshot.gameweek) ?? null;
}

export function fixtureText(fixture: FixtureRecord): string {
  return `${fixture.venue === "H" ? "home to" : "away at"} ${fixture.opponent_name || fixture.opponent}`;
}

function firstClause(text: string): string {
  const cut = text.split(/ - |\. /)[0];
  return cut.length > 64 ? cut.slice(0, 61).trimEnd() + "…" : cut;
}

// One plain sentence a manager would say about a player this week. The
// availability note always wins, because it is the thing most likely to change
// the decision; otherwise the fixture, with form added only when it stands out.
export function whyLine(player: PlayerRecord, fixture: FixtureRecord | null): string {
  if (isFlagged(player)) {
    if (player.news) return firstClause(player.news);
    const chance = player.chance_of_playing_next_round;
    return chance != null ? `${chance}% chance of playing` : "Availability in doubt";
  }
  if (!fixture) return "No fixture this gameweek";
  const where = fixtureText(fixture);
  const hot = Number(player.form) >= 5;
  if (fixture.difficulty <= 2) return `Kind fixture: ${where}${hot ? ", and in form" : ""}`;
  if (fixture.difficulty >= 4) return `Tough one: ${where}${hot ? ", but in form" : ""}`;
  return `${where.charAt(0).toUpperCase()}${where.slice(1)}${hot ? ", in good form" : ""}`;
}
