import { formatNumber } from './data.ts'

/** 与原 G2 版本一致的 SQLBOT 配色。 */
export const SQLBOT_PALETTE = [
  '#5B8FF9',
  '#5AD8A6',
  '#F6BD16',
  '#E8684A',
  '#6DC8EC',
  '#9270CA',
  '#FF9D4D',
  '#269A99',
  '#FF99C3',
  '#BDD2FD',
]

/**
 * 通用数值 formatter：不写死任何单位特例（label-not-convert，不换算、不折叠）。
 * - isPercent（数据含 "%"）→ 追加 %（echarts 里百分比值已是 85 而非 0.85）
 * - 任意 unit 字符串 → 原样作为后缀追加（"元/吨/件/pcs/美元…" 一视同仁）
 * - 无单位 → 仅千分符
 */
export function makeValueFormatter(isPercent = false, unit?: string) {
  return (value: any) => {
    if (isPercent) return `${formatNumber(value)}%`
    if (unit) return `${formatNumber(value)} ${unit}`
    return `${formatNumber(value)}`
  }
}
