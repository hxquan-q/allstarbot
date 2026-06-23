import { formatNumber } from './data.ts'
import { formatAxisWithUnit } from '../../../../utils/chartAxis.ts'

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
 * 统一数值 formatter：标注单位（label-not-convert，不换算数值，仅折叠 元→万/亿）。
 * - isPercent（数据含 "%"）优先 → 直接显示百分数，不走 formatAxisWithUnit 的 ×100（echarts 里值已是 85 而非 0.85）
 * - unit='元' → formatAxisWithUnit 折叠到 万/亿
 * - unit='%'（数据为 0-1 比例、未被 isPercent 捕获）→ formatAxisWithUnit ×100
 * - 其他 unit → 千分符 + 单位后缀
 */
export function makeValueFormatter(isPercent = false, unit?: string) {
  return (value: any) => {
    if (isPercent) return `${formatNumber(value)}%`
    if (unit === '元') return formatAxisWithUnit(value, '元')
    if (unit === '%') return formatAxisWithUnit(value, '%')
    if (unit) return `${formatNumber(value)} ${unit}`
    return `${formatNumber(value)}`
  }
}
