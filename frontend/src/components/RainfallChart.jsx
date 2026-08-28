export default function RainfallChart({ monthly }) {
  if (!monthly?.length) return null;
  const maxValue = Math.max(...monthly.map((item) => item.rainfall_mm), 1);
  const left = 32;
  const barWidth = 20;
  const gap = 5;
  const chartHeight = 112;
  const chartWidth = left + monthly.length * (barWidth + gap);
  const totalHeight = chartHeight + 34;
  const annualAverage = monthly.reduce((sum, item) => sum + item.rainfall_mm, 0);
  const summary = monthly.map((item) => `${item.month} ${item.rainfall_mm} millimetres`).join(', ');

  return (
    <figure className="rainfall-chart">
      <div className="chart-heading">
        <figcaption><span>Rainfall climatology</span><small>Average monthly distribution</small></figcaption>
        <strong>{Math.round(annualAverage).toLocaleString()} <small>mm/yr</small></strong>
      </div>
      <svg
        width="100%"
        height={totalHeight}
        viewBox={`0 0 ${chartWidth} ${totalHeight}`}
        role="img"
        aria-labelledby="rainfall-title rainfall-description"
      >
        <title id="rainfall-title">Average monthly rainfall in millimetres</title>
        <desc id="rainfall-description">{summary}</desc>
        <line x1={left - 4} y1="0" x2={left - 4} y2={chartHeight} className="chart-axis" />
        <line x1={left - 4} y1={chartHeight} x2={chartWidth} y2={chartHeight} className="chart-axis" />
        <text x={left - 7} y="9" textAnchor="end" className="chart-axis-label">{Math.round(maxValue)}</text>
        <text x={left - 7} y={chartHeight} textAnchor="end" className="chart-axis-label">0</text>
        {monthly.map((item, index) => {
          const height = (item.rainfall_mm / maxValue) * chartHeight;
          const x = left + index * (barWidth + gap);
          const y = chartHeight - height;
          return (
            <g key={item.month}>
              <rect x={x} y={y} width={barWidth} height={height} rx="2" className="rainfall-bar">
                <title>{`${item.month}: ${item.rainfall_mm} mm using ${item.valid_years} valid years`}</title>
              </rect>
              <text x={x + barWidth / 2} y={chartHeight + 14} textAnchor="middle" className="chart-month">
                {item.month.slice(0, 3)}
              </text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
