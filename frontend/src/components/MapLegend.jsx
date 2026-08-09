import React from 'react';

/**
 * MapLegend — overlay explaining the map layer colours.
 */
export default function MapLegend() {
  return (
    <div className="map-legend">
      <h4>Map Legend</h4>
      <div className="legend-items">
        <div className="legend-item">
          <span className="legend-swatch" style={{ background: '#38bdf8' }}></span>
          <span>Catchment Area</span>
        </div>
        <div className="legend-item">
          <span className="legend-swatch" style={{ background: '#fbbf24', border: '1px dashed #fbbf24' }}></span>
          <span>Available Land (CV)</span>
        </div>
        <div className="legend-item">
          <span className="legend-line" style={{ borderColor: '#a78bfa' }}></span>
          <span>Contour Lines</span>
        </div>
        <div className="legend-item">
          <svg width="14" height="14" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="8" fill="#ef4444" stroke="#fff" strokeWidth="2"/>
          </svg>
          <span>Proposed Pond</span>
        </div>
        <div className="legend-item">
          <svg width="14" height="14" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="8" fill="#3b82f6" stroke="#fff" strokeWidth="2"/>
          </svg>
          <span>Selected Centre</span>
        </div>
      </div>
    </div>
  );
}
