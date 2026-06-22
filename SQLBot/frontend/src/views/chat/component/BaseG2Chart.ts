import { BaseChart } from '@/views/chat/component/BaseChart.ts'
import { Chart } from '@antv/g2'

// 专业配色方案 - 适合数据可视化的高对比色板
const SQLBOT_PALETTE = [
  '#5B8FF9', // 蓝
  '#5AD8A6', // 绿
  '#F6BD16', // 黄
  '#E8684A', // 红
  '#6DC8EC', // 浅蓝
  '#9270CA', // 紫
  '#FF9D4D', // 橙
  '#269A99', // 深青
  '#FF99C3', // 粉
  '#BDD2FD', // 浅蓝灰
]

export abstract class BaseG2Chart extends BaseChart {
  chart: Chart

  constructor(id: string, name: string) {
    super(id, name)
    this.chart = new Chart({
      container: id,
      autoFit: true,
      padding: 'auto',
    })

    this.chart.theme({
      view: {
        viewFill: '#FFFFFF',
      },
      color: SQLBOT_PALETTE,
      category10: SQLBOT_PALETTE,
      category20: SQLBOT_PALETTE,
    })
  }

  render() {
    this.chart?.render()
  }

  destroy() {
    this.chart?.destroy()
  }
}
