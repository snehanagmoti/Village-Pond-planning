import React from 'react';

/**
 * RainfallChart — pure SVG bar chart showing monthly rainfall distribution.
 * No external charting library required.
 */
export default function RainfallChart({ monthly }) {
  if (!monthly || monthly.length === 0) return null;

  const maxVal = Math.max(...monthly.map(m => m.rainfall_mm), 1);
  const barWidth = 22;
  const gap = 4;
  const chartHeight = 110;
  const chartWidth = monthly.length * (barWidth + gap);
  const labelHeight = 20;
  const totalHeight = chartHeight + labelHeight + 24;

  return (
    <div className="rainfall-chart">
      <h3>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/>
        </svg>
        Monthly Rainfall
      </h3>
      <svg
        width="100%"
        height={totalHeight}
        viewBox={`0 0 ${chartWidth} ${totalHeight}`}
        preserveAspectRatio="xMidYMid meet"
      >
        {monthly.map((m, i) => {
          const barHeight = (m.rainfall_mm / maxVal) * chartHeight;
          const x = i * (barWidth + gap);
          const y = chartHeight - barHeight;

          return (
            <g key={i}>
              {/* Bar */}
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={barHeight}
                rx={3}
                ry={3}
                fill="url(#barGradient)"
                opacity={0.9}
              >
                <title>{`${m.month}: ${m.rainfall_mm} mm`}</title>
              </rect>
              {/* Value label (only show for bars tall enough) */}
              {barHeight > 18 && (
                <text
                  x={x + barWidth / 2}
                  y={y + 14}
                  textAnchor="middle"
                  fontSize="8"
                  fill="white"
                  fontWeight="600"
                >
                  {Math.round(m.rainfall_mm)}
                </text>
              )}
              {/* Month label */}
              <text
                x={x + barWidth / 2}
                y={chartHeight + 14}
                textAnchor="middle"
                fontSize="9"
                fill="#94a3b8"
              >
                {m.month.substring(0, 3)}
              </text>
            </g>
          );
        })}
        {/* Gradient definition */}
        <defs>
          <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#38bdf8"/>
            <stop offset="100%" stopColor="#0ea5e9"/>
          </linearGradient>
        </defs>
      </svg>
    </div>
  );
}
