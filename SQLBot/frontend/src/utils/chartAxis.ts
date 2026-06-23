// Pure helper: format an axis tick value with its inferred unit.
// Currency (元) collapses large numbers to 万/亿 so axis ticks stay readable.
// Used by the chart engine's axisLabel.formatter once wired in (browser-verified follow-up).
export function formatAxisWithUnit(value: number | string | null | undefined, unit: string | undefined): string {
  if (value === null || value === undefined || value === '') return ''
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return ''   // non-numeric (NaN / Infinity) → no axis label
  const u = unit || ''
  if (u === '元') {
    const abs = Math.abs(n)
    if (abs >= 1e8) return `${(n / 1e8).toFixed(2)} 亿元`
    if (abs >= 1e4) return `${(n / 1e4).toFixed(2)} 万元`
    return `${n} 元`
  }
  if (u === '%') return `${(n * 100).toFixed(0)} %`
  return u ? `${n} ${u}` : `${n}`
}
