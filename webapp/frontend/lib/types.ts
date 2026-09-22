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
  second_name: string;
  team: string;
  team_short: string;
  team_id: number;
  team_code: number;
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
  chance_of_playing_this_round: number | null;
  news_since_gw: number | null;
  cost_change_event: number;
  photo: string | null;
  photo_large?: string | null;
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
  prediction_timestamp: string | null;
  model: ModelSummary;
}

export interface SquadResult {
  ok: true;
  budget: number;
  spend: number;
  xi: PlayerRecord[];
  bench: PlayerRecord[];
  captain: PlayerRecord | null;
  vice_captain: PlayerRecord | null;
  xi_points: number;
  formation: string;
}

export interface TransferRow {
  transfers: number;
  gross: number;
  hit: number;
  net: number;
  gain: number;
  marginal: number | null;
  out: string[];
  in: string[];
  squad: PlayerRecord[];
  xi: PlayerRecord[];
}

export interface TransferFailure {
  transfers: number;
  status: string;
}

export interface TransferResult {
  ok: true;
  squad_value: number;
  bank: number;
  budget: number;
  free: number;
  hit_cost: number;
  decision_margin: number;
  rows: TransferRow[];
  failures: TransferFailure[];
  best: TransferRow | null;
  recommended: TransferRow | null;
  recommendation_edge: number | null;
  marginal_recommendation: boolean;
}

export interface ApiError {
  ok: false;
  error: string;
}

export interface PlayerHistoryRecord {
  season: string;
  gameweek: number;
  opponent: string;
  opponent_name: string;
  was_home: boolean;
  total_points: number;
  minutes: number;
  goals_scored: number;
  assists: number;
  clean_sheets: number;
  bonus: number;
  bps: number;
  ict_index: number;
}

export interface StoredSquad {
  season?: string;
  ids: number[];
  formation?: string;
  captainId?: number;
  viceCaptainId?: number;
}

export interface WatchlistPlayer {
  name: string;
  team: string;
  position: "GK" | "DEF" | "MID" | "FWD";
  value_m: number;
  predicted_points: number;
  points_per_million: number;
  selected_by?: number;
  opponent_team?: string;
  was_home?: boolean;
  has_prior_history?: boolean;
  status?: string;
  element?: number;
}

export interface WatchlistResult {
  ok: boolean;
  has_ownership: boolean;
  max_ownership: number;
  value: WatchlistPlayer[];
  differentials: WatchlistPlayer[];
  overpriced: WatchlistPlayer[];
  no_history: WatchlistPlayer[];
  no_history_total?: number;
}

export interface ChipRow {
  gw: number;
  matches: number;
  dgw_teams: number;
  blank_teams: number;
  avg_fdr: number;
  squad_playing?: number;
  squad_blanks?: number;
  opportunity: Partial<Record<ChipId, number | null>>;
}

export const CHIP_IDS = ["triple_captain", "bench_boost", "free_hit", "wildcard"] as const;
export type ChipId = (typeof CHIP_IDS)[number];
export type ChipState = "unused" | "used" | "expired";
export type ChipStatus = "play" | "watch" | "hold" | "unavailable";

export interface ChipInventory {
  first_half: Record<ChipId, ChipState>;
  second_half: Record<ChipId, ChipState>;
}

export interface ChipRecommendation {
  chip: ChipId;
  label: string;
  status: ChipStatus;
  candidate_gameweeks: number[];
  gw: number | null;
  candidate_gw: number | null;
  expected_gain: number | null;
  score_breakdown: Record<string, number | string | null>;
  reasons: string[];
  warnings: string[];
  inventory_set: "first_half" | "second_half";
  expires_after_gameweek: number;
  reason: string;
  confidence: "high" | "low" | "medium";
  note?: string;
  squad_gap?: number;
  bench_players?: ChipBenchPlayer[];
  captain_evidence?: ChipCaptainEvidence;
}

export interface ChipBenchPlayer {
  player: string;
  element: number | string;
  points: number;
  available: boolean;
}

export interface ChipCaptainEvidence {
  player: string;
  team: string;
  position: string;
  points: number | null;
  fixtures: number;
}

export interface ChipsResult {
  ok: boolean;
  first_gw: number;
  last_gw: number;
  any_dgw: boolean;
  any_bgw: boolean;
  has_squad: boolean;
  rows: ChipRow[];
  recommendations: ChipRecommendation[];
  unmapped_teams?: string[];
  current_gameweek: number;
  projection_mode: "fixture_signal" | "model_projection";
  inventory_status: "synced" | "not_synced";
  inventory_sync_state: "synced" | "not_synced";
  scheduled_gameweeks: number[];
}

