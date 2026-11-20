// Typed client for the LoadWise API. Types mirror the JSON contract (see FIELD_DICTIONARY.md).

export type Completeness = "complete" | "partial" | "missing" | "no_sessions";
export type MetricKey = "trimp" | "movement_load" | "hit_min" | "duration_min";
export type Severity = "error" | "warning" | "info";

export interface MetricBlock {
  value: number | null;
  valid_sessions: number;
  expected_sessions: number;
  completeness: Completeness;
}

export interface Athlete {
  athlete_id: string;
  label: string;
  source_label_variants: string[];
  session_records: number;
  wellness_records: number;
  history: { first_date: string | null; last_date: string | null; observed_days: number; observed_dates: string[];
    gaps: { from: string; to: string; days: number; status: string }[]; gap_policy: string };
}

export interface Summary {
  imports: number;
  session_records: number;
  sessions_included: number;
  sessions_excluded: number;
  sessions_rejected: number;
  excluded_exact_duplicates: number;
  possible_duplicate_sessions: number;
  wellness_records: number;
  athletes: number;
  resolved_dates: number;
  daily_records: number;
  daily_records_with_incomplete_metrics: number;
  multi_session_days: number;
  flags: Record<Severity, number>;
  flags_by_rule: Record<string, number>;
  date_range: { first: string | null; last: string | null };
}

export interface ImportRow {
  sha256: string;
  seq: number;
  filename: string;
  season_start_year: number | null;
  uploaded_at: string;
  size_bytes: number;
}

export interface Status {
  imports: ImportRow[];
  season_start_year: number | null;
  summary: Summary | null;
  generated_at: string | null;
  demo_available: boolean;
  demo_season_year: number;
}

export interface WindowTotal { value: number | null; observed_days: number; incomplete_days: number }

export interface SquadAthlete {
  athlete_id: string;
  label: string;
  first_date: string | null;
  last_date: string | null;
  observed_days: number;
  sessions: number;
  games: number;
  last7: Record<MetricKey, WindowTotal>;
  last28: Record<MetricKey, WindowTotal>;
  sparkline: { date: string; trimp: number | null }[];
  flags: Record<Severity, number>;
  incomplete_days: number;
}

export interface SummaryResponse {
  summary: Summary;
  squad: { reference_date: string | null; first_date: string; last_date: string; window_note: string; athletes: SquadAthlete[] };
  schedule: { note: string; game_session_dates: { date: string; athletes_with_game_session: number }[] };
}

export interface DailyRow {
  daily_id: string;
  athlete_id: string;
  athlete_label: string;
  date: string;
  study_day_index: number | null;
  session_count: number;
  sessions_by_type: { training: number; game: number; other: number };
  efficiency: number | null;
  efficiency_reason: string | null;
  trimp_per_min: number | null;
  trimp_per_min_reason: string | null;
  gd_labels: string[];
  gd_conflict: boolean;
  has_game: boolean;
  wellness_count: number;
  flag_counts: Record<Severity, number>;
  excluded_count: number;
  trimp: MetricBlock;
  movement_load: MetricBlock;
  hit_min: MetricBlock;
  duration_min: MetricBlock;
  [k: string]: unknown;
}

export interface Flag {
  flag_id: string;
  rule_code: string;
  severity: Severity;
  record_id: string | null;
  field: string | null;
  sheet: string | null;
  excel_row: number | null;
  original_value: unknown;
  explanation: string;
  aggregation_effect: string;
  athlete_id?: string | null;
  athlete_label?: string | null;
  date?: string | null;
}

export interface SessionRecord {
  record_id: string;
  provenance: { file: string; sheet: string; excel_row: number };
  athlete_id: string | null;
  athlete_label: string | null;
  date: string | null;
  study_day_index: number | null;
  measurement_type: string | null;
  session_bucket: "training" | "game" | "other";
  gd: string | null;
  start_time: string | null;
  end_time: string | null;
  crosses_midnight: boolean;
  metrics: Record<MetricKey, number | null>;
  source_ratios: { trimp_per_min: number | null; avg_movement_intensity: number | null };
  heart_rate: { avg_bpm: number | null; min_bpm: number | null; peak_bpm: number | null };
  source_reported: { acute_training_load: number | null; chronic_training_load: number | null; acwr: number | null };
  source_values: Record<string, unknown>;
  status: "included" | "excluded" | "rejected";
  status_reason: string | null;
  duplicate_of: string | null;
  override: { action: string; reason: string } | null;
  flag_ids: string[];
  values?: Record<string, number | null>;
}

export interface RawRecord {
  record_id: string;
  file: string;
  sheet: string;
  excel_row: number;
  cells: Record<string, unknown>;
}

export interface DailyDetail {
  daily: {
    date: string;
    athlete_label: string;
    totals: Record<MetricKey, MetricBlock>;
    breakdown: Record<"training" | "game" | "other", Record<MetricKey, MetricBlock>>;
    derived: Record<"efficiency" | "trimp_per_min", { value: number | null; reason: string | null }>;
    schedule: { gd_labels: string[]; gd_conflict: boolean };
    wellness: ({ record_id: string; excel_row: number } & Record<string, number | null | string>)[];
    study_day_index: number | null;
    avg_movement_intensity: { reason: string };
  };
  sessions: (SessionRecord & { raw: RawRecord | null })[];
  flags: Flag[];
}

export interface CalendarCell { value: number | null; completeness: Completeness; has_game: boolean; sessions: number }
export interface CalendarResponse {
  metric: MetricKey;
  dates: string[];
  athletes: { athlete_id: string; label: string; cells: (CalendarCell | null)[] }[];
}

export interface ReviewItem {
  kind: "exact_duplicate" | "possible_duplicate" | "manual_override";
  record_id: string;
  athlete_id: string;
  athlete_label: string;
  date: string;
  excel_row: number;
  file: string;
  measurement_type: string | null;
  start_time: string | null;
  end_time: string | null;
  metrics: Record<MetricKey, number | null>;
  status: string;
  status_reason: string | null;
  override: { action: string; reason: string } | null;
  related: string[];
}

export interface Preview {
  file: string;
  sheets_present: string[];
  sheets: { role: string; sheet: string; present: boolean; header_row: number | null; records: number;
    columns: number; unavailable: string[]; messages: string[] }[];
  needs_season_year: boolean;
  date_samples: { excel_row: number; raw: unknown; resolved: { iso: string | null; error: string | null } }[];
  rollover: { month: number; month_name: string; records: number; example: string; resolved_year: number | null }[];
}

export type Activity = "training" | "game" | "rest";
export const PLANNING_FIELDS = [
  "original_team", "original_extra", "other_recorded", "team_min", "team_max", "extra_min", "extra_max",
  "ml_limit", "trimp_limit", "ml_buffer", "trimp_buffer", "weekly_ml_limit", "weekly_trimp_limit",
] as const;
export type PlanningKey = (typeof PLANNING_FIELDS)[number];
export type Planning = Record<PlanningKey, number>;

export interface PlanConfig {
  athlete: string;
  start: string;
  planning: Planning;
  schedule: Activity[];
  step: 1 | 5 | 10;
  objective: "terminal" | "cumulative";
  allow_pooled: boolean;
  overrides: Record<string, Partial<Planning>>;
}

export interface PlanMeta {
  roster: { athlete_id: string; label: string; training_days: number; measured_mip_days: number; last_date: string | null }[];
  first_start: string | null;
  last_start: string | null;
  schedule: Activity[];
  fitting_period: { first_date: string; last_date: string };
  demo: PlanConfig | null;
  scope: string;
}

export interface PlanHistory {
  athlete_id: string;
  label: string;
  start: string;
  week_dates: string[];
  planning: Planning;
  reason: string | null;
  personalized: boolean;
  in_fitting_period: boolean;
  features: Record<string, number | null> | null;
  history: { date: string; mip1: number | null; movement_load: number | null; training_trimp: number | null; recorded_duration_min: number | null }[];
}

export interface PlanDay {
  day: number; date: string; kind: Activity; team: number; extra: number; duration: number | null;
  mip1: number | null; movement_load: number | null; training_trimp: number | null; spline: number | null;
}

export interface PlanSummary {
  plan: PlanDay[]; weekly_ml: number; weekly_trimp: number; ml_margin: number; trimp_margin: number;
  day7_mip: number | null; mip_sum: number;
}

export interface PlanResult extends PlanSummary {
  athlete: string; start: string; pooled: boolean; reason: string | null; objective: "terminal" | "cumulative";
  original: { day: number; date: string; team: number; extra: number; duration: number; mip1: number | null; movement_load: number | null; training_trimp: number | null }[];
  alternative: PlanSummary | null;
  explanation: string;
  limitation: string;
}

export type Decision = "accepted" | "rejected" | "modified";

/** One day as the coach set it in the Modify editor. */
export interface EditedDay { day: number; kind: Activity; team: number; extra: number }

export interface EvaluatedDay extends PlanDay { supported: boolean | null }

export interface EvaluatedPlan extends PlanSummary {
  start: string;
  plan: EvaluatedDay[];
  pooled: boolean;
  warnings: { day: number | null; code: string; message: string }[];
}

export interface FeedbackRecord {
  id: number;
  created_at: string;
  athlete_id: string;
  athlete_label: string;
  start: string;
  decision: Decision;
  rating: number | null;
  /** Accept and reject ratings point in opposite directions; never compare them directly. */
  rating_scale: "acceptance" | "rejection" | null;
  comment: string | null;
  config: PlanConfig;
  proposal: PlanResult;
  modified: { days: EditedDay[]; evaluation: EvaluatedPlan } | null;
}

export interface FeedbackIn {
  config: PlanConfig;
  proposal: PlanResult;
  decision: Decision;
  rating?: number;
  comment?: string;
  modified?: { days: EditedDay[] };
}

export interface ModelEvidence {
  comparison: { target: string; specification: string; model: string; selected: boolean; parameters: string;
    val_rmse: number; val_r2: number; val_n: number; test_mae: number; test_rmse: number; test_r2: number; test_n: number }[];
  importance: { target: string; model: string; group: string; mean_delta_rmse: number; sd_delta_rmse: number }[];
}

export class ApiError extends Error {
  constructor(message: string, public status: number, public code?: string) { super(message); }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
    let detail = r.statusText, code: string | undefined;
    try { const j = await r.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); code = j.code; } catch { /* not json */ }
    throw new ApiError(detail, r.status, code);
  }
  return r.json() as Promise<T>;
}

const qs = (p: Record<string, string | number | undefined | null>) => {
  const s = new URLSearchParams();
  Object.entries(p).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") s.set(k, String(v)); });
  const str = s.toString();
  return str ? `?${str}` : "";
};

function form(file: File, year: number | null) {
  const f = new FormData();
  f.append("file", file);
  if (year !== null) f.append("season_start_year", String(year));
  return f;
}

export const api = {
  status: () => req<Status>("/api/status"),
  summary: (ref?: string) => req<SummaryResponse>(`/api/summary${qs({ ref })}`),
  athletes: () => req<Athlete[]>("/api/athletes"),
  daily: (p: { athlete?: string; date_from?: string; date_to?: string } = {}) => req<DailyRow[]>(`/api/daily${qs(p)}`),
  dailyDetail: (athlete: string, date: string) => req<DailyDetail>(`/api/daily/${athlete}/${date}`),
  calendar: (metric: MetricKey) => req<CalendarResponse>(`/api/calendar${qs({ metric })}`),
  flags: () => req<Flag[]>("/api/flags"),
  record: (id: string) => req<{ record: SessionRecord; raw: RawRecord | null; flags: Flag[] }>(`/api/records/${encodeURIComponent(id)}`),
  review: () => req<ReviewItem[]>("/api/review"),
  setOverride: (record_id: string, action: "include" | "exclude", reason: string) =>
    req<unknown>("/api/overrides", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ record_id, action, reason }) }),
  clearOverride: (record_id: string) => req<unknown>(`/api/overrides/${encodeURIComponent(record_id)}`, { method: "DELETE" }),
  previewFile: (file: File, year: number | null) => req<Preview>("/api/preview", { method: "POST", body: form(file, year) }),
  previewDemo: (year: number | null) => req<Preview>(`/api/preview/demo${qs({ season_start_year: year })}`),
  importFile: (file: File, year: number | null) => req<{ status: string }>("/api/imports", { method: "POST", body: form(file, year) }),
  importDemo: (year: number) => req<{ status: string }>(`/api/imports/demo${qs({ season_start_year: year })}`, { method: "POST" }),
  reset: () => req<unknown>("/api/store", { method: "DELETE" }),
  planMeta: () => req<PlanMeta>("/api/plan/meta"),
  planHistory: (athlete: string, start: string) => req<PlanHistory>(`/api/plan/history${qs({ athlete, start })}`),
  planOptimize: (config: PlanConfig) =>
    req<PlanResult>("/api/plan/optimize", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config) }),
  planEvaluate: (config: PlanConfig, days: EditedDay[]) =>
    req<EvaluatedPlan>("/api/plan/evaluate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ config, days }) }),
  planFeedbackCreate: (body: FeedbackIn) =>
    req<FeedbackRecord>("/api/plan/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  planFeedbackList: (athlete?: string) => req<FeedbackRecord[]>(`/api/plan/feedback${qs({ athlete })}`),
  planFeedbackGet: (id: number) => req<FeedbackRecord>(`/api/plan/feedback/${id}`),
  planModels: () => req<ModelEvidence>("/api/plan/models"),
};
