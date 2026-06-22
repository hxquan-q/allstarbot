const { checkIsPercent, getAxesWithFilter } = require('./utils');

function getScatterOptions(base_options, axis, data) {
    const axes = getAxesWithFilter(axis);

    if (axes.x.length === 0 || axes.y.length === 0) {
        return base_options;
    }

    const x = axes.x;
    const y = axes.y;
    const series = axes.series;
    const _data = checkIsPercent([x[0], y[0]], data);

    return {
        ...base_options,
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
            },
            y: {
                title: y[0].name,
                labelFontSize: 12,
            },
        },
        scale: {
            x: { nice: true },
            y: { nice: true, type: 'linear' },
        },
    };
}

module.exports = { getScatterOptions };
