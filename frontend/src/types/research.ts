export type DataClass = 'measured' | 'simulated' | 'synthetic_example' | string
export type Level = 'observed' | 'supported' | 'hypothesis' | 'inconclusive'

export interface Evidence { metric: string; value: unknown; unit: string; baseline: unknown; note: string }
export interface Insight {
  id: string; level: Level; statement: string; evidence: Evidence[]; data_class: DataClass
  validation_status: string; limitations: string[]
}
export interface SelfCheck { name: string; passed: boolean | null; value?: number | null; criterion?: string; unit?: string }
export interface ReportSections { tested: string; changed: string; graph: string; pca: string; model: string; trust: string; conclusion: string }

export interface Common { data_class: DataClass; insights: Insight[]; report: ReportSections; self_checks?: SelfCheck[] }

export interface SweepRow {
  level: number; error?: string; x: number[]; raw: number[]; processed: number[]; processed_x: number[]
  status: string; snr: number | null; top1: string; top1_score: number; truth_score: number | null; margin: number | null
  top1_correct: boolean | null; correct: boolean | null; reasons: string[]
  mean_peak_displacement_cm1: number | null; n_baseline_peaks_found: number; n_baseline_peaks: number
  pca_position: number[]; model_prediction?: { label: string; confidence: number; trained_on: string }
}
export interface Sweep extends Common {
  kind: string; label: string; perturbation_class: string; level_unit: string; neutral_level: number; truth: string | null
  baseline: { status: string; top1: string; top1_score: number }; baseline_x: number[]; baseline_processed: number[]
  rows: SweepRow[]; first_failure: Record<string, { level: number; reason: string }>
  reference_pca: { ids: string[]; scores: number[][]; explained_variance_ratio: number[]; note: string }
  distinction_note: string; limitations: string[]; sample: string; seed: number
}
export interface MatrixItem {
  kind: string; label: string; class: string; unit: string; levels: number[]; truth_score: (number | null)[]
  correct: (boolean | null)[]; status: string[]; first_failure: Record<string, { level: number; reason: string }>; neutral: number
}
export interface Matrix { experiments: MatrixItem[]; held_constant: string; truth: string | null; sample: string }

export interface PeakChange {
  baseline_position: number; matched: boolean; delta_position_cm1?: number; delta_relative_height?: number
  height_ratio?: number | null; delta_fwhm_cm1?: number | null
}
export interface CondExp {
  label: string; data_class: DataClass; metadata: Record<string, number | string | null>
  changed_parameters: string[]; constant_parameters: string[]; unrecorded_parameters: string[]; design: string; warnings: string[]
  x: number[]; raw: number[]; raw_x: number[]; processed: number[]; difference_x: number[]; difference: number[]
  similarity_to_baseline: number; snr: number | null; status: string; top1: string; top1_score: number
  same_top1_as_baseline: boolean; peak_changes: PeakChange[]; n_baseline_peaks_matched: number
  mean_delta_position_cm1: number | null; mean_delta_fwhm_cm1: number | null; median_height_ratio: number | null
}
export interface Conditions extends Common {
  baseline: { label: string; data_class: DataClass; metadata: Record<string, number | string | null>; x: number[]; raw: number[]; raw_x: number[]; processed: number[]; snr: number | null; top1: string }
  experiments: CondExp[]; limitations: string[]
}
export interface ExcitationInfo { excitation_nm: number; laser_color: string; stokes_wavelength_nm: [number, number]; anti_stokes_wavelength_nm: [number, number]; explanation: string }

export interface PcaResult extends Common {
  grid: number[]; n_spectra: number; n_components: number; scaling: string; explained_variance_ratio: number[]
  cumulative_variance: number[]; ml_backend: string
  scores: { spectrum_id: string; specimen_id: string; material: string; condition: string; scores: number[] }[]
  loadings: { pc: number; values: number[]; top_regions: { from: number; to: number; peak_abs_loading: number; sign: string }[] }[]
  factor_association: { factor: string; n_groups: number; eta_squared_per_pc: number[] | null; silhouette: number | null; note: string }[]
  warnings: string[]; interpretation_note: string
}

export interface ClassReport {
  accuracy: number; macro_f1: number; labels: string[]; confusion_matrix: number[][]; n: number
  per_class: { label: string; precision: number; recall: number; f1: number; support: number }[]
  expected_calibration_error?: number
}
export interface BenchModel {
  model: string; status: string; reason?: string; family?: string; train_seconds?: number; inference_ms_per_spectrum?: number
  model_size_bytes?: number; parameters?: number; hyperparameters?: Record<string, unknown>; note?: string
  clean_report?: ClassReport; by_scenario?: Record<string, { accuracy: number; macro_f1: number }>
}
export interface Benchmark extends Common {
  warning: string; labels: string[]; class_counts: Record<string, number>; imbalance_ratio: number
  splits: Record<string, number | string>; scenarios: string[]; models: BenchModel[]
  out_of_distribution: { detector: string; flagged_fraction_by_scenario: Record<string, number>; note: string }
  config: Record<string, unknown>; environment: Record<string, string | null>; protocol: string[]; reference_framework: string
}

export interface Fidelity { mean: number; sd: number; n: number }
export interface Translation extends Common {
  warning: string; fitted_parameters: Record<string, { shift_cm1: number; gain: number; standard_pairs: number }>
  fidelity: Record<string, { aggregate: Record<string, Fidelity | null> }>
  comparison_vs_resample_only: Record<string, Record<string, { mean_change_vs_baseline: number; fraction_of_pairs_improved: number; improved: boolean; direction_better: string } | null>>
  downstream: Record<string, string | { accuracy: number; macro_f1: number; n: number }> | null
  runtime_seconds: Record<string, number>; n_evaluation_pairs: number; calibration_standard: string
  example: { x: number[]; target: number[] | null; source_resampled: number[] | null; translated: Record<string, number[]> }
  neural_translation: { status: string; reason: string }; limitations: string[]
  source_description: { steps: { kind: string; params: Record<string, number> }[]; grid_step_cm1: number }
}

export interface Study { kind: string; title: string; result: Common }
