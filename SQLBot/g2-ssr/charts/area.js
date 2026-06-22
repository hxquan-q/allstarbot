const { getAxesWithFilter, processMultiQuotaData } = require('./utils');

function getAreaOptions(base_options, axis, data) {
    const axes = getAxesWithFilter(axis);

    if (axes.x.length === 0 || axes.y.length === 0) {
        return base_options;
    }

    let config = {
        data: data,
        y: axes.y,
        series: axes.series,
    };

    if (axes.multiQuota.length > 0) {
        config = processMultiQuotaData(axes.x, config.y, axes.multiQuota, axes.multiQuotaName, config.data);
    }

    const x = axes.x;
    const y = config.y;
    const series = config.series;

    const options = {
        ...base_options,
        type: 'view',
        data: config.data,
        encode: {
            x: x[0].value,
            y: y[0].value,
            color: series.length > 0 ? series[0].value : undefined,
        },
        axis: {
            x: {
                title: false,
                labelFontSize: 12,
            },
            y: {
                title: false,
                labelFontSize: 12,
            },
        },
        scale: {
            x: { nice: true },
            y: { nice: true, type: 'linear' },
        },
        children: [
            {
                type: 'area',
                style: {
                    fillOpacity: 0.25,
                },
            },
            {
                type: 'line',
                style: {
                    lineWidth: 2,
                },
            },
        ],
    };

    if (series.length > 0) {
        options.transform = [{ type: 'stackY' }];
    }

    return options;
}

module.exports = { getAreaOptions };
