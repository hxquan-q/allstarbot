const { endsWith } = require('lodash')

/**
 * 为数值添加千分符，保持原有小数位数不变
 * 纯字符串处理，避免精度丢失
 * 支持：正负整数、小数、字符串格式的数值
 */
function formatNumber(value) {
  if (value === null || value === undefined || value === '') {
    return value
  }

  let str
  if (typeof value === 'string') {
    str = value.trim()
  } else if (typeof value === 'number') {
    str = String(value)
  } else {
    return value
  }

  const match = str.match(/^([+-])?(\d+)(\.(\d+))?$/)
  if (!match) {
    return value
  }

  const sign = match[1] || ''
  const intPart = match[2]
  const decPart = match[3] || ''

  const formattedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')

  return sign + formattedInt + decPart
}

function getAxesWithFilter(axes) {
  const groups = {
    x: [],
    y: [],
    series: [],
    multiQuota: [],
    multiQuotaName: undefined,
  }

  // 分组
  axes.forEach((axis) => {
    if (axis.type === 'x') groups.x.push(axis)
    else if (axis.type === 'y') groups.y.push(axis)
    else if (axis.type === 'series') groups.series.push(axis)
    else if (axis.type === 'other-info') groups.multiQuotaName = axis.value
  })

  // 应用过滤规则
  if (groups.series.length > 0) {
    groups.y = groups.y.slice(0, 1)
  } else {
    const multiQuotaY = groups.y.filter((item) => item['multi-quota'] === true)
    groups.multiQuota = multiQuotaY.map((item) => item.value)
    if (multiQuotaY.length > 0) {
      groups.y = multiQuotaY
    }
  }

  return groups
}

function processMultiQuotaData(
  x,
  y,
  multiQuota,
  multiQuotaName = 'sqlbot_auto_series',
  data,
) {
  const _list = []
  const _map = {}
  y.forEach((axis) => {
    _map[axis.value] = axis.name
  })
  for (const datum of data) {
    multiQuota.forEach((quota) => {
      const _data = {}
      for (const xAxis of x) {
        _data[xAxis.value] = datum[xAxis.value]
      }
      _data['sqlbot_auto_quota'] = datum[quota]
      _data['sqlbot_auto_series'] = _map[quota]
      _list.push(_data)
    })
  }

  return {
    data: _list,
    y: [{ name: 'sqlbot_auto_quota', value: 'sqlbot_auto_quota', type: 'y' }],
    series: [{ name: multiQuotaName, value: 'sqlbot_auto_series', type: 'series' }],
  }
}

function toChartNumber(value) {
  if (value === null || value === undefined || value === '') {
    return value
  }

  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0
  }

  const strValue = String(value).trim()
  if (!strValue) {
    return value
  }

  const isPercent = endsWith(strValue, '%')
  const numericText = (isPercent ? strValue.slice(0, -1) : strValue)
    .replace(/,/g, '')
    .trim()
  const numericPattern = /^[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[+-]?\d+)?$/i

  if (!numericPattern.test(numericText)) {
    return isPercent ? 0 : value
  }

  const numValue = Number(numericText)
  if (!Number.isFinite(numValue)) {
    return isPercent ? 0 : value
  }

  return numValue
}

function checkIsPercent(valueAxes, data) {
  const result = {
    isPercent: false,
    data: [],
  }

  // 深拷贝原始数据
  for (let i = 0; i < data.length; i++) {
    result.data.push({ ...data[i] })
  }

  for (let i = 0; i < data.length; i++) {
    for (const valueAxis of valueAxes) {
      const value = data[i]?.[valueAxis.value]
      if (value !== null && value !== undefined && value !== '') {
        const strValue = String(value).trim()
        if (endsWith(strValue, '%')) {
          result.isPercent = true
        }
        result.data[i][valueAxis.value] = toChartNumber(value)
      }
    }
  }

  return result
}

module.exports = { checkIsPercent, formatNumber, getAxesWithFilter, processMultiQuotaData }
