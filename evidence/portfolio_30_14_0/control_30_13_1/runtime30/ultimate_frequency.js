"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.trainingFrequencies = trainingFrequencies;
const ultimate_stats_1 = require("./ultimate_stats");
/** Descriptive training-only spectrum. Peaks never become an automatic trade signal. */
function trainingFrequencies(data, through) {
    return data.series.map((series) => {
        const sessions = data.sessions.filter((s) => s.close <= through), samples = [];
        for (const session of sessions) {
            const bars = series.bars.filter((b) => b.t >= session.open &&
                b.end <= session.close &&
                b.availableAt <= through);
            for (let i = 1; i < bars.length; i++)
                if (bars[i].t === bars[i - 1].end)
                    samples.push({
                        minute: Math.round((bars[i].t - session.open) / 60000),
                        value: Math.log(bars[i].c / bars[i - 1].c),
                    });
        }
        const buckets = new Map();
        for (const s of samples) {
            if (!buckets.has(s.minute))
                buckets.set(s.minute, []);
            buckets.get(s.minute).push(s.value);
        }
        const x = samples.map((s) => s.value - (0, ultimate_stats_1.mean)(buckets.get(s.minute))), mu = (0, ultimate_stats_1.mean)(x), variance = (0, ultimate_stats_1.mean)(x.map((v) => (v - mu) ** 2));
        const autocorrelation = (absolute) => {
            const y = absolute ? x.map(Math.abs) : x, m = (0, ultimate_stats_1.mean)(y), v = (0, ultimate_stats_1.mean)(y.map((z) => (z - m) ** 2));
            return [1, 2, 3, 6, 12].map((lag) => ({
                lagBars: lag,
                value: v > 1e-20 && y.length > lag
                    ? (0, ultimate_stats_1.mean)(y.slice(lag).map((z, i) => (z - m) * (y[i] - m))) / v
                    : null,
            }));
        };
        const periods = [3, 6, 12, 24, 48, 78];
        const spectrum = periods.map((period) => {
            let re = 0, im = 0;
            for (let j = 0; j < x.length; j++) {
                const weight = x.length > 1
                    ? 0.5 - 0.5 * Math.cos((2 * Math.PI * j) / (x.length - 1))
                    : 1;
                re += weight * x[j] * Math.cos((2 * Math.PI * j) / period);
                im += weight * x[j] * Math.sin((2 * Math.PI * j) / period);
            }
            return {
                periodBars: period,
                periodTradingMinutes: period * 5,
                normalizedPower: variance > 1e-20 ? (re * re + im * im) / (x.length * variance) : null,
            };
        });
        return {
            symbol: series.symbol,
            through,
            observations: x.length,
            status: x.length >= 100 ? "TRAINING_DIAGNOSTIC" : "INSUFFICIENT_EVIDENCE",
            autocorrelation: autocorrelation(false),
            absoluteReturnAutocorrelation: autocorrelation(true),
            intraday: [...buckets].map(([minute, values]) => ({
                minuteFromOpen: minute,
                meanReturn: (0, ultimate_stats_1.mean)(values),
                observations: values.length,
            })),
            spectrum,
            scope: "CONCATENATED_TRADING_TIME_DESCRIPTIVE_ONLY_NO_CALENDAR_FREQUENCY_OR_ALPHA_CLAIM",
            nextExperimentRequiredToTradePeaks: true,
        };
    });
}
