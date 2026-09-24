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
  market_prices_updated_at: string | null;
  // False when the backend has no usable live prices; budgets, transfers and
  // chips are refused (503, code "market_prices_unavailable") until it does.
  market_prices_available?: boolean;
  market_prices_error?: string | null;
  predictions_older_than_market: boolean;
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

export interface TransferRow extends SquadResult {
  transfers: number;
  gross: number;
  hit: number;
  net: number;
  gain: number;
  marginal: number | null;
  out: string[];
  in: string[];
  squad: PlayerRecord[];
  market_value: number;
  selling_value: number;
  bank_after: number;
  captained_total: number;
}

export interface TransferFailure {
  transfers: number;
  status: string;
}

export interface TransferResult {
  ok: true;
  squad_value: number;
  selling_value: number;
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
  current_lineup: SquadResult;
}

export interface ApiError {
  ok: false;
  error: string;
  // Machine-readable slug, e.g. "invalid_field", "unknown_player",
  // "market_prices_unavailable", "refresh_auth_required".
  code?: string;
  // The request field at fault, when one is.
  field?: string;
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

export type PriceBasis = "imported" | "manual" | "estimated";

export interface OwnedPrice {
  purchaseTenths: number;
  // Retained from an import for a one-time consistency check against the
  // selling-price formula; not read back as a computation input.
  sellingTenths?: number;
}

export interface SquadFinance {
  version: 2;
  bankTenths: number;
  ownedPrices: Record<number, OwnedPrice>;
  priceBasis: PriceBasis;
  marketPriceAsOf?: string | null;
  lineupGameweek?: number;
}

export interface StoredSquad {
  season?: string;
  ids: number[];
  formation?: string;
  captainId?: number;
  viceCaptainId?: number;
  xiIds?: number[];
  benchIds?: number[];
  /** @deprecated superseded by finance.bankTenths; kept for reading pre-finance saves. */
  bank?: number;
  source?: "manual" | "manager" | "optimizer";
  sourceEntryId?: number;
  sourceManagerName?: string;
  sourceTeamName?: string;
  sourceGameweek?: number;
  finance?: SquadFinance;
}

export interface ManagerSearchCandidate {
  entry_id: number;
  manager_name: string;
  team_name: string;
  overall_rank: number | null;
  total_points: number | null;
}

export interface LeagueStandingsEntry {
  entry_id: number;
  manager_name: string;
  team_name: string;
  rank: number | null;
  total_points: number | null;
}

export interface LeagueStandingsResult {
  ok: true;
  league_id: number;
  league_name: string;
  page: number;
  has_next: boolean;
  entries: LeagueStandingsEntry[];
}

export interface LeagueNameSearchResult {
  ok: true;
  league_id: number;
  league_name: string;
  query: string;
  results: LeagueStandingsEntry[];
  scanned_from_page: number;
  scanned_through_page: number;
  scanned_entries: number;
  next_cursor: number | null;
  has_more: boolean;
  scope: "league_pages";
  interrupted?: boolean;
  interrupted_code?: "upstream_rate_limited" | "upstream_unavailable";
}

export interface ManagerPick {
  element: number;
  position: number;
  multiplier: number;
  is_captain: boolean;
  is_vice_captain: boolean;
  purchase_price: number;
  selling_price: number;
}

export interface ManagerLineup {
  ok: true;
  fetched_at: string;
  source: "fpl_public_api";
  manager: ManagerSearchCandidate;
  requested_gameweek: number | null;
  lineup_gameweek: number;
  bank: number | null;
  team_value: number | null;
  event_points: number | null;
  event_rank: number | null;
  overall_rank: number | null;
  total_points: number | null;
  active_chip: string | null;
  missing_elements: number[];
  picks: ManagerPick[];
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
  projected_gain: Partial<Record<ChipId, number | null>>;
  fixture_signal_index: Partial<Record<ChipId, number | null>>;
}

export const CHIP_IDS = ["triple_captain", "bench_boost", "free_hit", "wildcard"] as const;
export type ChipId = (typeof CHIP_IDS)[number];
export type ChipState = "unused" | "used" | "expired";
export type ChipStatus = "play" | "watch" | "hold" | "unavailable";

export interface ChipInventory {
  first_half: Record<ChipId, ChipState>;
  second_half: Record<ChipId, ChipState>;
}

export interface ChipDecisionPolicy {
  minimum_projected_gain: number;
  uncertainty_note: string;
  basis: string;
}

export interface ChipCaptainEvidence {
  chip: "triple_captain";
  captain: {
    element: number | string;
    name: string;
    team: string;
    position: string;
    projected_points: number | null;
    fixtures: number;
    available: boolean;
  } | null;
  normal_captain_total: number;
  triple_captain_total: number | null;
  incremental_gain: number | null;
}

export interface ChipBenchEvidence {
  chip: "bench_boost";
  ordered_bench: ChipBenchPlayer[];
  bench_total: number;
}

export interface ChipFreeHitEvidence {
  chip: "free_hit";
  current_xi_captain_total: number;
  optimized_xi_captain_total: number | null;
  raw_delta: number | null;
  current_xi_total: number;
  optimized_xi_total: number | null;
  current_captain_points: number | null;
  optimized_captain_points: number | null;
  changed_player_count: number;
}

export interface ChipWildcardEvidence {
  chip: "wildcard";
  current_cumulative_total: number;
  optimized_cumulative_total: number;
  weekly_deltas: Record<string, number>;
  horizon_length: number;
  changed_player_count: number;
}

export type ChipEvidence =
  | ChipCaptainEvidence
  | ChipBenchEvidence
  | ChipFreeHitEvidence
  | ChipWildcardEvidence;

export interface ChipAlternative {
  chip: ChipId;
  gw: number;
  projected_gain: number | null;
  fixture_signal_index: number | null;
  evidence: ChipEvidence | null;
}

export interface ChipRecommendationBase {
  label: string;
  status: ChipStatus;
  projection_mode: "fixture_signal" | "model_projection";
  candidate_gameweeks: number[];
  gw: number | null;
  candidate_gw: number | null;
  projected_gain: number | null;
  fixture_signal_index: number | null;
  alternatives: ChipAlternative[];
  runner_up_gameweek: number | null;
  gap_to_runner_up: number | null;
  decision_policy: ChipDecisionPolicy;
  reasons: string[];
  warnings: string[];
  inventory_set: "first_half" | "second_half";
  expires_after_gameweek: number;
  confidence: "high" | "low" | "medium";
  formula?: string;
}

export type ChipRecommendation =
  | (ChipRecommendationBase & { chip: "triple_captain"; evidence: ChipCaptainEvidence | null })
  | (ChipRecommendationBase & { chip: "bench_boost"; evidence: ChipBenchEvidence | null })
  | (ChipRecommendationBase & { chip: "free_hit"; evidence: ChipFreeHitEvidence | null })
  | (ChipRecommendationBase & { chip: "wildcard"; evidence: ChipWildcardEvidence | null });

export interface ChipBenchPlayer {
  player: string;
  element: number | string;
  points: number;
  available: boolean;
}


export const CHIPS_CONTRACT_VERSION = 2;

export interface ChipsResult {
  ok: boolean;
  contract_version: number;
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
  projection_source: string;
  projection_generated_at: string | null;
  projection_gameweeks: number[];
  requested_horizon: number;
  evaluated_horizon: number;
  coverage_warning: string | null;
  data_quality: "complete_horizon" | "fixture_signal_only";
  methodology_version: string;
  decision_policy: ChipDecisionPolicy;
}

