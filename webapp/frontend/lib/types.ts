// Mirrors webapp/platform_data.py and the JSON shapes returned by webapp/app.py.
// Every field here comes from the local FPL season snapshot or the model's
// predictions_next_gw.csv export -- nothing is fabricated client-side.

export interface FixtureRecord {
  gameweek: number;
  opponent: string;
  opponent_name: string;
  venue: "H" | "A";
  difficulty: number;
  kickoff_time: string;
}

export interface TeamRecord {
  id: number;
  name: string;
  short_name: string;
  code: number;
  fixtures: FixtureRecord[];
}

export interface PlayerRecord {
  element: number;
  name: string;
  web_name: string;
  first_name: string;
  team: string;
  team_short: string;
  position: "GK" | "DEF" | "MID" | "FWD";
  value_m: number;
  status: string;
  news: string | null;
  form: number;
  total_points: number;
  minutes: number;
  starts?: number | null;
  goals_scored: number;
  assists: number;
  clean_sheets: number;
  bonus: number;
  bps: number;
  ict_index: number;
  expected_goals: number;
  expected_assists: number;
  expected_goal_involvements?: number | null;
  saves?: number | null;
  goals_conceded?: number | null;
  yellow_cards?: number | null;
  red_cards?: number | null;
  selected_by: number;
  transfers_in_event: number;
  transfers_out_event: number;
  chance_of_playing_next_round: number | null;
  photo: string | null;
  country?: string | null;
  flag?: string | null;
  birth_date?: string | null;
  team_join_date?: string | null;
  squad_number?: string | null;
  predicted_points: number | null;
  points_per_million: number | null;
  opponent_team?: string | null;
  was_home?: boolean | null;
  has_prior_history?: boolean | null;
}

export interface ModelSummary {
  [position: string]: {
    model: string;
    features: number;
    test_r2: number;
  };
}

export interface PlatformSnapshot {
  ok: true;
  available: boolean;
  message: string;
  season: string;
  gameweek: number | null;
  players: PlayerRecord[];
  teams: TeamRecord[];
  prediction_available: boolean;
  prediction_error: string | null;
  model: ModelSummary;
}

export interface SquadResult {
  ok: true;
  budget: number;
  spend: number;
  xi: PlayerRecord[];
  bench: PlayerRecord[];
  captain: PlayerRecord | null;
  xi_points: number;
  formation: string;
}

export interface TransferRow {
  transfers: number;
  gross: number;
  hit: number;
  gain: number;
  out: string[];
  in: string[];
}

export interface TransferResult {
  ok: true;
  best: TransferRow | null;
  rows: TransferRow[];
}

export interface ApiError {
  ok: false;
  error: string;
}
