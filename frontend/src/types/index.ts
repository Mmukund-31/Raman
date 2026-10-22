export interface Peak { position: number; height: number; relative_height: number; prominence: number; near_boundary: boolean }
export interface Match { reference_id: string; name: string; score: number; coverage: number; overlap: [number, number] | null }
export interface Result {
  sample_id: string; source: string; status: 'ok' | 'inconclusive'; quality_warnings: string[]; snr: number
  excitation_nm: number | null; x: number[]; raw: number[]; baseline: number[]; processed: number[]
  peaks: Peak[]; matches: Match[]; top_matches: Match[]; parameters: Record<string, string | number>
  limitations: string[]; software_version: string; timestamp: string; is_diagnostic: false
}
export interface Example { sample_id: string; description: string; category: string }
export interface Options {
  baseline: boolean; smooth: boolean; window: number; poly: number
  normalize: 'none' | 'vector' | 'max'; prominence: number
}
export const defaultOptions: Options = { baseline: true, smooth: true, window: 11, poly: 3, normalize: 'vector', prominence: 0.05 }
