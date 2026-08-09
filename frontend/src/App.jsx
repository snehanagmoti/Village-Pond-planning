import React, { useState, useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polygon, Polyline, Tooltip, useMapEvents, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import axios from 'axios';
import L from 'leaflet';

// Components
import SearchBar from './components/SearchBar';
import MapLegend from './components/MapLegend';
import RainfallChart from './components/RainfallChart';

// Fix Leaflet default icon issue with bundlers
import iconUrl from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

const DefaultIcon = L.icon({ iconUrl, shadowUrl: iconShadow, iconSize: [25, 41], iconAnchor: [12, 41] });
L.Marker.prototype.options.icon = DefaultIcon;

// Custom icon for the proposed pond
const PondIcon = L.divIcon({
  html: '<div style="background:#ef4444;width:16px;height:16px;border-radius:50%;border:3px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.4)"></div>',
  className: '',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

const API_URL = "http://localhost:8000/api";

/* ── Map click handler ─────────────────────────────────── */
function LocationMarker({ position, setPosition, onAnalyze }) {
  useMapEvents({
    click(e) {
      setPosition(e.latlng);
      onAnalyze(e.latlng);
    },
  });

  return position ? (
    <Marker position={position}>
      <Popup><strong>Selected Village Centre</strong><br />{position.lat.toFixed(4)}, {position.lng.toFixed(4)}</Popup>
    </Marker>
  ) : null;
}

/* ── Fly map to location when search result is selected ── */
function FlyTo({ center }) {
  const map = useMap();
  const prevCenter = useRef(null);

  useEffect(() => {
    if (center && JSON.stringify(center) !== JSON.stringify(prevCenter.current)) {
      prevCenter.current = center;
      map.flyTo(center, 13, { duration: 1.5 });
    }
  }, [center, map]);

  return null;
}

/* ── Main Application ────────────────────────────────── */
function App() {
  const [position, setPosition] = useState(null);
  const [analysisData, setAnalysisData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [flyTarget, setFlyTarget] = useState(null);
  const [error, setError] = useState(null);
  const [radiusKm, setRadiusKm] = useState(2.0);
  const [villageName, setVillageName] = useState(null);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  const formatPolygon = (poly) => poly.map(p => [p.lat, p.lng]);

  const runAnalysis = async (latlng, name = null) => {
    setLoading(true);
    setError(null);
    setAnalysisData(null);
    try {
      const resp = await axios.post(`${API_URL}/analyze`, {
        center: { lat: latlng.lat, lng: latlng.lng },
        radius_km: radiusKm,
        village_name: name || villageName,
      });
      setAnalysisData(resp.data);
      // Auto-zoom to analysis area after click-to-analyze
      setFlyTarget([latlng.lat, latlng.lng]);
    } catch (err) {
      console.error("Analysis error:", err);
      const detail = err.response?.data?.detail;
      setError(detail ? `Analysis failed: ${detail}` : "Analysis failed. Is the backend running on port 8000?");
    } finally {
      setLoading(false);
    }
  };

  const handleVillageSelect = (result) => {
    const latlng = { lat: result.lat, lng: result.lng };
    const name = result.display_name.split(',')[0];
    setPosition(latlng);
    setVillageName(name);
    setFlyTarget([result.lat, result.lng]);
    runAnalysis(latlng, name);
  };

  const handleReset = () => {
    setAnalysisData(null);
    setPosition(null);
    setError(null);
    setFlyTarget(null);
    setVillageName(null);
    setShowHistory(false);
  };

  const loadHistory = async () => {
    try {
      const resp = await axios.get(`${API_URL}/history`, { params: { limit: 10 } });
      setHistory(resp.data || []);
      setShowHistory(true);
    } catch (err) {
      console.error("History load error:", err);
    }
  };

  // Colour helper for contour lines based on elevation
  const getContourColor = (elevation, minElev, maxElev) => {
    const t = maxElev > minElev ? (elevation - minElev) / (maxElev - minElev) : 0.5;
    const r = Math.round(167 + t * 60);
    const g = Math.round(139 - t * 60);
    const b = Math.round(250 - t * 80);
    return `rgb(${r},${g},${b})`;
  };

  return (
    <div className="app-container">
      {/* ── Map ──────────────────────────────────────── */}
      <div className="map-container">
        <MapContainer center={[20.5937, 78.9629]} zoom={5} style={{ height: "100%", width: "100%" }}>
          <TileLayer
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            attribution='Tiles &copy; Esri'
          />
          <FlyTo center={flyTarget} />
          <LocationMarker position={position} setPosition={setPosition} onAnalyze={runAnalysis} />

          {analysisData && (
            <>
              {/* Catchment Area */}
              <Polygon
                positions={formatPolygon(analysisData.catchment_polygon)}
                pathOptions={{ color: '#38bdf8', weight: 2, fillOpacity: 0.15, fillColor: '#38bdf8' }}
              >
                <Tooltip sticky>Catchment Area</Tooltip>
              </Polygon>

              {/* Contour Lines with elevation labels */}
              {analysisData.contours.map((contour, idx) => {
                const minE = analysisData.elevation_stats.min_elevation;
                const maxE = analysisData.elevation_stats.max_elevation;
                return (
                  <Polyline
                    key={idx}
                    positions={formatPolygon(contour.points)}
                    pathOptions={{
                      color: getContourColor(contour.elevation, minE, maxE),
                      weight: 1.5,
                      opacity: 0.7,
                      dashArray: '6 3',
                    }}
                  >
                    <Tooltip sticky>{contour.elevation}m</Tooltip>
                  </Polyline>
                );
              })}

              {/* Available / Government Land (from CV analysis) */}
              <Polygon
                positions={formatPolygon(analysisData.government_land_polygon)}
                pathOptions={{ color: '#fbbf24', weight: 2, fillOpacity: 0.1, dashArray: '5 5' }}
              >
                <Tooltip sticky>Available Land (Detected via CV)</Tooltip>
              </Polygon>

              {/* Proposed Pond Location */}
              <Marker position={[analysisData.pond.lat, analysisData.pond.lng]} icon={PondIcon}>
                <Popup>
                  <strong>Proposed Pond</strong><br />
                  Depth: {analysisData.pond.depth_m}m<br />
                  Capacity: {analysisData.pond.capacity_m3.toLocaleString()} m³<br />
                  <em style={{fontSize:'11px',opacity:0.7}}>Placed at lowest elevation in catchment</em>
                </Popup>
              </Marker>
            </>
          )}
        </MapContainer>

        {/* Map Legend overlay */}
        {analysisData && <MapLegend />}
      </div>

      {/* ── Sidebar ──────────────────────────────────── */}
      <div className="sidebar">
        <div className="header">
          <h1>Pond Planning AI</h1>
          <p>Village-level terrain & rainfall analysis</p>
        </div>

        {/* Search */}
        <SearchBar onSelect={handleVillageSelect} />

        {/* Radius slider */}
        <div className="radius-control">
          <label htmlFor="radius-slider">
            Analysis Radius: <strong>{radiusKm.toFixed(1)} km</strong>
          </label>
          <input
            id="radius-slider"
            type="range"
            min="0.5"
            max="5.0"
            step="0.5"
            value={radiusKm}
            onChange={(e) => setRadiusKm(parseFloat(e.target.value))}
          />
        </div>

        {/* Instructions */}
        {!analysisData && !loading && !error && !showHistory && (
          <div className="instruction-box">
            Search for a village above or click anywhere on the map to select a location and run the analysis.
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="loading-box">
            <div className="spinner"></div>
            <div>
              <strong>Analyzing terrain...</strong>
              <p className="loading-detail">Fetching elevation data, running D8 watershed analysis, downloading satellite imagery...</p>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="error-box">{error}</div>
        )}

        {/* Results */}
        {analysisData && (
          <>
            {/* Elevation Stats */}
            <div className="section-label">Elevation Profile</div>
            <div className="stats-grid">
              <div className="stat-card">
                <span className="stat-label">Min Elevation</span>
                <div><span className="stat-value">{analysisData.elevation_stats.min_elevation}</span><span className="stat-unit"> m</span></div>
              </div>
              <div className="stat-card">
                <span className="stat-label">Max Elevation</span>
                <div><span className="stat-value">{analysisData.elevation_stats.max_elevation}</span><span className="stat-unit"> m</span></div>
              </div>
              <div className="stat-card">
                <span className="stat-label">Mean Elevation</span>
                <div><span className="stat-value">{analysisData.elevation_stats.mean_elevation}</span><span className="stat-unit"> m</span></div>
              </div>
              <div className="stat-card">
                <span className="stat-label">Relief</span>
                <div><span className="stat-value">{analysisData.elevation_stats.relief}</span><span className="stat-unit"> m</span></div>
              </div>
            </div>

            {/* Hydrology Stats */}
            <div className="section-label">Hydrology & Runoff</div>
            <div className="stats-grid">
              <div className="stat-card">
                <span className="stat-label">Catchment Area</span>
                <div><span className="stat-value">{(analysisData.runoff_stats.catchment_area_sqm / 10000).toFixed(2)}</span><span className="stat-unit"> ha</span></div>
              </div>
              <div className="stat-card">
                <span className="stat-label">Annual Rainfall</span>
                <div><span className="stat-value">{analysisData.rainfall_data.annual_avg_mm}</span><span className="stat-unit"> mm</span></div>
              </div>
              <div className="stat-card">
                <span className="stat-label">Est. Runoff</span>
                <div><span className="stat-value">{analysisData.runoff_stats.estimated_volume_m3.toLocaleString()}</span><span className="stat-unit"> m³</span></div>
              </div>
              <div className="stat-card">
                <span className="stat-label">Runoff Coeff.</span>
                <div><span className="stat-value">{analysisData.runoff_stats.runoff_coefficient}</span></div>
              </div>
            </div>

            {/* Land Analysis */}
            <div className="section-label">Land Cover (OpenCV)</div>
            <div className="stats-grid cols-2">
              <div className="stat-card">
                <span className="stat-label">Barren Land</span>
                <div><span className="stat-value">{(analysisData.land_analysis.barren_ratio * 100).toFixed(1)}</span><span className="stat-unit">%</span></div>
              </div>
              <div className="stat-card">
                <span className="stat-label">Adjusted Coeff.</span>
                <div><span className="stat-value">{analysisData.land_analysis.adjusted_runoff_coeff}</span></div>
              </div>
            </div>

            {/* Rainfall Chart */}
            <RainfallChart monthly={analysisData.rainfall_data.monthly} />

            {/* Pond Recommendation */}
            <div className="pond-recommendation">
              <h3>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/>
                </svg>
                Recommended Pond
              </h3>
              <div className="pond-details">
                <div className="detail-row">
                  <span>Location</span>
                  <strong>{analysisData.pond.lat.toFixed(4)}°, {analysisData.pond.lng.toFixed(4)}°</strong>
                </div>
                <div className="detail-row">
                  <span>Target Depth</span>
                  <strong>{analysisData.pond.depth_m} m</strong>
                </div>
                <div className="detail-row">
                  <span>Storage Capacity</span>
                  <strong>{analysisData.pond.capacity_m3.toLocaleString()} m³</strong>
                </div>
                <div className="detail-row">
                  <span>Surface Area</span>
                  <strong>{Math.round(analysisData.pond.surface_area_sqm).toLocaleString()} m²</strong>
                </div>
              </div>
            </div>

            <button id="reset-btn" className="btn" onClick={handleReset}>
              Reset Analysis
            </button>
          </>
        )}

        {/* History Button (show when idle) */}
        {!analysisData && !loading && (
          <button id="history-btn" className="btn btn-secondary" onClick={loadHistory}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{marginRight:'6px',verticalAlign:'middle'}}>
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
            View Past Analyses
          </button>
        )}

        {/* History Panel */}
        {showHistory && history.length > 0 && !analysisData && (
          <div className="history-panel">
            <div className="section-label">Analysis History</div>
            {history.map((item) => (
              <div key={item.id} className="history-card">
                <div className="history-header">
                  <strong>{item.village_name || `(${item.center_lat.toFixed(3)}°, ${item.center_lng.toFixed(3)}°)`}</strong>
                  <span className="history-date">{new Date(item.created_at).toLocaleDateString()}</span>
                </div>
                <div className="history-stats">
                  {item.annual_rainfall_mm != null && <span>🌧 {item.annual_rainfall_mm.toFixed(0)} mm</span>}
                  {item.estimated_volume_m3 != null && <span>💧 {item.estimated_volume_m3.toLocaleString()} m³</span>}
                  {item.pond_depth_m != null && <span>📏 {item.pond_depth_m} m deep</span>}
                </div>
              </div>
            ))}
          </div>
        )}

        {showHistory && history.length === 0 && !analysisData && (
          <div className="instruction-box">No past analyses found.</div>
        )}
      </div>
    </div>
  );
}

export default App;
