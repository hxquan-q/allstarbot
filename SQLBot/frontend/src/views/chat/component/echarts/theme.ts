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

/** 坐标轴刻度 formatter：千分符 + 百分号。 */
export function axisLabelFormatter(isPercent = false) {
  return (value: any) => `${formatNumber(value)}${isPercent ? '%' : ''}`
}

/** tooltip / label 的数值 formatter。 */
export function valueFormatter(isPercent = false) {
  return (value: any) => `${formatNumber(value)}${isPercent ? '%' : ''}`
}
