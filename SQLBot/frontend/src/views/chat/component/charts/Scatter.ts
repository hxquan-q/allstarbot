import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import {
  checkIsPercent,
  formatNumber,
  getAxesWithFilter,
} from '@/views/chat/component/charts/utils.ts'

export class Scatter extends BaseG2Chart {
  constructor(id: string) {
    super(id, 'scatter')
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>) {
    super.init(axis, data)

    const axes = getAxesWithFilter(this.axis)

    if (axes.x.length == 0 || axes.y.length == 0) {
      console.debug({ instance: this })
      return
    }

    const x = axes.x
    const y = axes.y
    const series = axes.series

    const _data = checkIsPercent([x[0], y[0]], data)

    console.debug({ 'render-info': { x: x, y: y, series: series, data: _data }, instance: this })

    const options: G2Spec = {
      ...this.chart.options(),
      type: 'point',
      data: _data.data,
      encode: {
        x: x[0].value,
        y: y[0].value,
        color: series.length > 0 ? series[0].value : undefined,
        shape: 'point',
      },
      style: {
        size: 6,
        fillOpacity: 0.7,
        stroke: '#fff',
        lineWidth: 1,
      },
      axis: {
        x: {
          title: x[0].name,
          labelFontSize: 12,
          labelAutoHide: true,
          labelAutoRotate: false,
        },
        y: {
          title: y[0].name,
          labelFormatter: (value: any) => {
            return String(formatNumber(value))
          },
        },
      },
      scale: {
        x: {
          nice: true,
        },
        y: {
          nice: true,
          type: 'linear',
        },
      },
      interaction: {
        elementHighlight: { background: true },
        tooltip: { series: series.length > 0 },
      },
      tooltip: (data: any) => {
        const items: any = {
          name: series.length > 0 ? data[series[0].value] : y[0].name,
          value: `${x[0].name}: ${formatNumber(data[x[0].value])}, ${y[0].name}: ${formatNumber(data[y[0].value])}${_data.isPercent ? '%' : ''}`,
        }
        return items
      },
    } as G2Spec

    this.chart.options(options)
  }
}
