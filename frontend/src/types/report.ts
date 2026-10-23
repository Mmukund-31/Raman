import type { Match, Options, Peak, Provenance } from './index'
import type { Insight, SelfCheck } from './research'

export type SectionStatus = 'complete' | 'partial' | 'insufficient_data' | 'error'
export type SectionId = 'validation' | 'spectrum' | 'peaks' | 'matching' | 'conditions' | 'sensitivity' | 'pca' | 'benchmark' | 'translation' | 'quality'

export interface Section<D = Record<string, never>> {
  title: string; status: SectionStatus; summary: string; reason: string | null; requirements: string[]
  data: D; data_class: string | null
}

export interface ValidationData {
  points: number; range_cm1: [number, number]; median_step_cm1: number; coordinate_input: string; converted_from_wavelength: boolean
  warnings: string[]; additional_spectra: { name: string; points: number; range_cm1: [number, number] }[]
  rejected_additional_spectra: { name: string; error: string }[]
}
export interface SpectrumData {
  x: number[]; raw: number[]; baseline: number[]; processed: number[]; peaks: Peak[]
  parameters: Record<string, string | number>; units: { x: string; raw: string; processed: string }
}
export interface PeakRow extends Peak { region_hints: string[]; near_reference_bands: string[] }
export interface PeaksData { peaks: PeakRow[]; band_note: string; tolerance_cm1: number; prominence_frac?: number }
export interface MatchWithAgreement extends Match {
  peak_agreement: { tolerance_cm1: number; reference_peaks_in_overlap: number; matched: { reference: number; sample: number }[]; unmatched_reference: number[] }
}
export interface MatchingData { matches: MatchWithAgreement[]; similarity_note: string; claim_allowed: boolean; references_all_synthetic: boolean }
export interface ComparisonExp {
  label: string; x: number[]; similarity_to_baseline: number; n_baseline_peaks_matched: number; peak_changes: unknown[]
  mean_delta_position_cm1: number | null; top1: string; status: string; difference_x: number[]; difference: number[]; processed: number[]
}
export interface ConditionsData {
  metadata: Record<string, string | number | null>; recorded: Record<string, string | number>; missing: string[]
  labels: Record<string, [string, string]>; laser_color: string | null; power_density_mW_per_um2: number | null
  excitation?: { excitation_nm: number; laser_color: string; stokes_wavelength_nm: [number, number]; explanation: string }
  excitation_error?: string; comparison?: { experiments: ComparisonExp[]; note: string; baseline: { x: number[]; processed: number[] } }
  comparison_error?: string
}
export interface SensitivityRow {
  level: number; error?: string; status: string; top1: string; top1_score: number; same_top1: boolean; snr: number | null
  mean_peak_displacement_cm1: number | null; n_baseline_peaks_found: number; n_baseline_peaks: number
  processed: number[]; processed_x: number[]; truth_score: number | null
}
export interface SensitivityData {
  label: string; level_unit: string; neutral_level: number; truth: string | null
  baseline: { status: string; top1: string; top1_score: number }; baseline_x: number[]; baseline_processed: number[]
  rows: SensitivityRow[]; stable_within_cm1: number | null; top1_changed_at: number[]; tested_range_cm1: number
  distinction_note: string; limitations: string[]; self_checks: SelfCheck[]; insights: Insight[]
}
export interface PcaData {
  grid: number[]; n_spectra: number; n_components: number; explained_variance_ratio: number[]; cumulative_variance: number[]
  scores: { spectrum_id: string; material: string; role: string; scores: number[] }[]
  loadings: { pc: number; values: number[]; top_regions: { from: number; to: number; peak_abs_loading: number; sign: string }[] }[]
  warnings: string[]; alignment_notes: string[]; interpretation_note: string; insights: Insight[]
}
export interface QualityData {
  status: 'ok' | 'inconclusive'; verdict: string; conclusive: false; snr: number | null; warnings: string[]
  thresholds: Record<string, string | number>; error_sources: string[]; limitations: string[]; conclusive_note: string
}

export interface Brief {
  report_id: string; verdict: 'Provisional match' | 'Inconclusive'; headline: string; match_claimed: boolean
  metrics: { label: string; value: string; note?: string }[]; findings: string[]
  peaks: { position: number; relative_height: number; assignment: string | null; reference: string | null }[]
  references: { name: string; score: number; coverage: number }[]; robustness: string | null
  limitations: string[]; recommendations: string[]; not_performed: { title: string; reason: string }[]; methods: string
}

export interface EvidenceFact { id: string; label: string; text: string; section: string }
export interface Explanation {
  source: 'llm_verified' | 'rule_based'; headline: string; what_we_found: { text: string; evidence: string[] }[]
  how_sure: string; what_this_does_not_mean: string[]; next_steps: string[]; glossary: { term: string; plain: string }[]
  evidence: EvidenceFact[]; note: string; model?: string; llm_status?: string
}
export interface VisualSummary {
  confidence: { level: 0 | 1 | 2 | 3; label: string; reason: string }
  overlay: {
    x: number[]; sample: number[]; reference: { x: number[]; y: number[] } | null; reference_name: string | null
    reference_category?: string; peaks: number[]; peak_heights: number[]
  }
  candidates: { items: { name: string; score: number; category?: string; top: boolean }[]; threshold: number; named: boolean }
  checks: { id: string; label: string; passed: boolean; detail: string }[]
}
export interface EvaluationSummary {
  headline: string | null; date: string; n_materials: number; n_reference_spectra: number
  clean: { n: number; answered_fraction: number; accuracy_when_answered: number | null }
  negative_control: { n: number; false_match_rate: number }
}

export interface FullReport {
  report_version: string; software_version: string; generated_at: string; sample_id: string; source: string; brief: Brief
  declared_origin: Origin; data_provenance: Provenance & { sample: { declared_origin?: string } }; is_diagnostic: false
  inputs: { n_spectra: number; additional: string[]; options: Options; metadata: Record<string, unknown>; truth_label: string | null }
  executive_summary: {
    analyzed: string; findings: string[]; confidence: string; status: 'ok' | 'inconclusive'
    availability: { id: SectionId; title: string; status: SectionStatus }[]
  }
  sections: {
    validation: Section<ValidationData>; spectrum: Section<SpectrumData>; peaks: Section<PeaksData>; matching: Section<MatchingData>
    conditions: Section<ConditionsData>; sensitivity: Section<SensitivityData>; pca: Section<PcaData>
    benchmark: Section<Record<string, number>>; translation: Section<Record<string, never>>; quality: Section<QualityData>
  }
  conclusion: { meaning: string[]; does_not_prove: string[]; next_steps: string[] }
  explanation?: Explanation
  evaluation?: EvaluationSummary | null
  visual?: VisualSummary
}

export type Origin = 'unknown' | 'measured' | 'synthetic'
export type StageStatus = 'pending' | 'running' | 'done' | 'skipped' | 'error'
export interface StageEvent { event: 'stage'; stage: string; label: string; status: Exclude<StageStatus, 'pending'>; detail?: string | null; completed: number; total: number }
export interface ResultEvent { event: 'result'; report: FullReport }
export interface ErrorEvent { event: 'error'; stage: string; message: string }
export type ProgressEvent = StageEvent | ResultEvent | ErrorEvent

export interface Conditions {
  temperature: string; temperature_unit: 'K' | 'C'; laser_power: string; laser_power_unit: 'mW' | 'W' | 'uW'
  exposure_s: string; incidence_angle_deg: string; collection_angle_deg: string; geometry: string; instrument: string; spot_diameter_um: string
}
export const emptyConditions: Conditions = {
  temperature: '', temperature_unit: 'C', laser_power: '', laser_power_unit: 'mW', exposure_s: '', incidence_angle_deg: '',
  collection_angle_deg: '', geometry: '', instrument: '', spot_diameter_um: '',
}

export interface AnalysisInput {
  file: File | null; example: string; extras: { file: File; label: string }[]; primaryLabel: string
  excitation: string; origin: Origin; conditions: Conditions; options: Options
}
