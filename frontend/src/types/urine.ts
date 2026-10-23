export type UrineDatasetId = 'trial' | 'zenodo'

export interface UrineDataset {
  dataset_id: UrineDatasetId; name: string; category: 'synthetic' | 'measured'; excitation_nm: number; n_spectra: number
  license: string; citation?: string | null; doi?: string | null; url?: string | null; design?: string | null; caveat?: string | null
  groups?: Record<string, number> | null; arms?: Record<string, number> | null
}

export interface IndexSummary { n: number; p5: number; q1: number; median: number; q3: number; p95: number; values: number[] }
export type IndexKey = 'glucose' | 'ketones' | 'urea'

export interface UrineSample {
  sample_id: string; group: string; week: number | null; participant: string | null; response: string | null; class: string | null
  pc: number[]; indices: Record<IndexKey, number | null>; reference_glucose_mg_dl: number | null; cv_probability: number | null
}

export interface TrialData {
  weeks: number[]
  participants: { participant: string; arm: string; response: string; glucose_index: (number | null)[]; reference_glucose: number[] }[]
  cohort_means: { cohort: 'control' | 'responder' | 'non-responder'; label: string; n: number; mean: number[]; se: number[] }[]
  responder_surface: { weeks: number[]; grid: number[]; z: number[][] }
  calibration: { slope: number; intercept: number; r: number; r2: number; n: number } | null
  responder_median_drop: number | null
}

export interface UrineStudy {
  dataset: Partial<UrineDataset> & { instrument?: string; processing?: string }
  n_spectra: number; groups: { id: string; label: string; n: number }[]; positive_group: string; grid: number[]
  mean_spectra: { group: string; label: string; n: number; mean: number[]; sd: number[] }[]
  difference: { label: string; y: number[] }
  bands: { position: number; solute: string; label: string }[]
  indices: Record<IndexKey, { label: string; note: string; bands: number[] }>
  index_stats: Record<IndexKey, Record<string, IndexSummary | null>>
  pca: { explained_variance_ratio: number[]; loadings: number[][] }
  samples: UrineSample[]
  classification: {
    positive: string; n: number; n_positive: number; n_folds: number; method: string; auc: number; accuracy: number
    sensitivity: number; specificity: number; confusion: { tp: number; fn: number; fp: number; tn: number }; threshold: number
    roc: { fpr: number[]; tpr: number[] }
  }
  waterfall: { sample_id: string; group: string; glucose_index: number | null; y: number[] }[]
  trial: TrialData | null
  processing: string; disclaimer: string
}

export interface UrineResult {
  dataset: UrineDatasetId; dataset_name: string; dataset_category: string; grid: number[]; processed: number[]
  covered_cm1: [number, number]; indices: Record<IndexKey, number | null>; index_position: Record<IndexKey, Record<string, number | null>>
  pc: number[]; nearest_group: string; nearest_group_label: string; similarity_to_positive: number; positive_group: string
  positive_label: string; flags: string[]; disclaimer: string; sample_name: string; warnings: string[]
}

export interface UrineExample { sample_id: string; file: string; description: string; category: string; concentrations_mg_dl: Record<string, number> }

export interface PersonalIndex {
  label: string; values: (number | null)[]; baseline: number | null; latest: number | null; change: number | null; change_pct: number | null
  rcv: number; significant: boolean; reference_range: [number, number] | null; in_reference_range: (boolean | null)[]
}

export interface UrineParticipant {
  participant: string; arm: string; response: string; group: string; weeks: number[]; reference_group: string; reference_label: string
  indices: Record<IndexKey, PersonalIndex>
  reference_change: Record<IndexKey, { sd_within: number; cv_assumed: number; n_people: number; rcv_at_zero: number }>
  reference_glucose_mg_dl: (number | null)[]; grid: number[]; spectra: number[][]; difference: number[]; pc_path: number[][]
  insights: string[]; disclaimer: string
}
