import { useEffect, useRef, useState } from 'react';
import {
  MapContainer,
  Marker,
  Polygon,
  Polyline,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

import { api, apiErrorMessage } from './api';
import SearchBar from './components/SearchBar';
import MapLegend from './components/MapLegend';
import RainfallChart from './components/RainfallChart';
import iconUrl from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';


const DefaultIcon = L.icon({ iconUrl, shadowUrl: iconShadow, iconSize: [25, 41], iconAnchor: [12, 41] });
L.Marker.prototype.options.icon = DefaultIcon;
const PondIcon = L.divIcon({ html: '<span class="pond-marker" aria-hidden="true"></span>', className: '', iconSize: [22, 22], iconAnchor: [11, 11] });
const imageryTileUrl = import.meta.env.VITE_IMAGERY_TILE_URL
  || 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const imageryAttribution = import.meta.env.VITE_IMAGERY_ATTRIBUTION
  || 'Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community';


function SelectionMarker({ position, onSelect }) {
  useMapEvents({
    click(event) {
      onSelect({ lat: event.latlng.lat, lng: event.latlng.lng }, null);
    },
  });
  return position ? (
    <Marker position={position}>
      <Popup>Selected analysis centre<br />{position.lat.toFixed(5)}, {position.lng.toFixed(5)}</Popup>
    </Marker>
  ) : null;
}


function FlyTo({ center }) {
  const map = useMap();
  const previous = useRef(null);
  useEffect(() => {
    if (center && `${center[0]}:${center[1]}` !== previous.current) {
      previous.current = `${center[0]}:${center[1]}`;
      map.flyTo(center, 13, { duration: 0.8 });
    }
  }, [center, map]);
  return null;
}


const polygonPositions = (polygon = []) => polygon.map((point) => [point.lat, point.lng]);
const numberOrDash = (value, digits = 1) => value == null ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
const MAX_CONTOUR_FILE_BYTES = 15 * 1024 * 1024;
const hasAnalysisContract = (value) => Boolean(
  value
  && ['complete', 'degraded', 'incomplete'].includes(value.analysis_status)
  && value.quality?.sources
  && Array.isArray(value.quality.warnings)
  && value.elevation_stats
  && value.runoff_stats
  && value.rainfall_data
  && value.land_analysis
  && value.persistence,
);
const hasContourContract = (value) => Boolean(
  value
  && value.analysis_status === 'degraded'
  && value.contour_summary
  && value.grid
  && value.pond_location
  && value.catchment
  && Array.isArray(value.catchment.boundary)
  && Array.isArray(value.study_area_boundary)
  && value.quality?.sources
  && Array.isArray(value.quality.warnings),
);


export default function App() {
  const [position, setPosition] = useState(null);
  const [villageName, setVillageName] = useState(null);
  const [coordinates, setCoordinates] = useState({ lat: '', lng: '' });
  const [radiusKm, setRadiusKm] = useState(2);
  const [analysis, setAnalysis] = useState(null);
  const [contourAnalysis, setContourAnalysis] = useState(null);
  const [contourFile, setContourFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('Select a location, review the radius, then start the screening analysis.');
  const [flyTarget, setFlyTarget] = useState(null);
  const analysisAbortRef = useRef(null);
  const analysisSequenceRef = useRef(0);

  useEffect(() => () => {
    analysisSequenceRef.current += 1;
    analysisAbortRef.current?.abort();
  }, []);

  const selectLocation = (nextPosition, name = null) => {
    analysisSequenceRef.current += 1;
    analysisAbortRef.current?.abort();
    setLoading(false);
    setPosition(nextPosition);
    setCoordinates({ lat: nextPosition.lat.toFixed(6), lng: nextPosition.lng.toFixed(6) });
    setVillageName(name);
    setAnalysis(null);
    setContourAnalysis(null);
    setError('');
    setFlyTarget([nextPosition.lat, nextPosition.lng]);
    setStatus('Location selected. Review the analysis radius and press Start screening analysis.');
  };

  const handleVillageSelect = (result) => {
    selectLocation({ lat: result.lat, lng: result.lng }, result.display_name.split(',')[0]);
  };

  const submitCoordinates = (event) => {
    event.preventDefault();
    const lat = Number(coordinates.lat);
    const lng = Number(coordinates.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || lat < -85 || lat > 85 || lng < -180 || lng > 180) {
      setError('Enter a latitude from −85 to 85 and longitude from −180 to 180.');
      return;
    }
    selectLocation({ lat, lng }, null);
  };

  const runAnalysis = async () => {
    if (!position) return;
    analysisAbortRef.current?.abort();
    const controller = new AbortController();
    analysisAbortRef.current = controller;
    const sequence = ++analysisSequenceRef.current;
    setLoading(true);
    setError('');
    setAnalysis(null);
    setContourAnalysis(null);
    setStatus('Analysis in progress. External sources and hydrology quality are being checked.');
    try {
      const response = await api.post('/analyze', {
        center: position,
        radius_km: radiusKm,
        village_name: villageName,
      }, { signal: controller.signal });
      if (sequence !== analysisSequenceRef.current) return;
      if (!hasAnalysisContract(response.data)) {
        throw new Error('The API returned an unsupported analysis contract.');
      }
      setAnalysis(response.data);
      setStatus(`Analysis finished with ${response.data.analysis_status} status.`);
      setFlyTarget([position.lat, position.lng]);
    } catch (requestError) {
      if (requestError?.code === 'ERR_CANCELED') {
        if (sequence === analysisSequenceRef.current) setStatus('Analysis cancelled.');
        return;
      }
      if (sequence === analysisSequenceRef.current) {
        const message = apiErrorMessage(requestError, 'Analysis failed. Check backend readiness and try again.');
        setError(message);
        setStatus(`Analysis failed: ${message}`);
      }
    } finally {
      if (sequence === analysisSequenceRef.current) setLoading(false);
    }
  };

  const selectContourFile = (event) => {
    const file = event.target.files?.[0] || null;
    setContourFile(file);
    setContourAnalysis(null);
    setError('');
    setStatus(file
      ? `${file.name} selected. Press Analyze contour map to upload and compute the catchment.`
      : 'Select a KML or KMZ contour map to start the file-based analysis.');
  };

  const runContourAnalysis = async (event) => {
    event?.preventDefault?.();
    if (!contourFile) {
      setError('Select a KML or KMZ contour file first.');
      return;
    }
    if (contourFile.size > MAX_CONTOUR_FILE_BYTES) {
      setError('The contour file exceeds the 15 MiB upload limit.');
      return;
    }

    analysisAbortRef.current?.abort();
    const controller = new AbortController();
    analysisAbortRef.current = controller;
    const sequence = ++analysisSequenceRef.current;
    const body = new FormData();
    body.append('contour_file', contourFile);
    setLoading(true);
    setError('');
    setAnalysis(null);
    setContourAnalysis(null);
    setStatus('Uploading contours and deriving the terrain, catchment and candidate pond point.');
    try {
      const response = await api.post('/analyze-contour', body, { signal: controller.signal });
      if (sequence !== analysisSequenceRef.current) return;
      if (!hasContourContract(response.data)) {
        throw new Error('The API returned an unsupported contour-analysis contract.');
      }
      setContourAnalysis(response.data);
      setPosition(null);
      setVillageName(null);
      setCoordinates({ lat: '', lng: '' });
      setStatus('Contour analysis finished. The result is screening-only because the surface is interpolated from contour lines.');
      setFlyTarget([response.data.pond_location.lat, response.data.pond_location.lng]);
    } catch (requestError) {
      if (requestError?.code === 'ERR_CANCELED') {
        if (sequence === analysisSequenceRef.current) setStatus('Analysis cancelled.');
        return;
      }
      if (sequence === analysisSequenceRef.current) {
        const message = apiErrorMessage(requestError, 'Contour analysis failed. Check the file and backend readiness, then try again.');
        setError(message);
        setStatus(`Contour analysis failed: ${message}`);
      }
    } finally {
      if (sequence === analysisSequenceRef.current) setLoading(false);
    }
  };

  const cancelAnalysis = () => analysisAbortRef.current?.abort();

  const reset = () => {
    analysisSequenceRef.current += 1;
    analysisAbortRef.current?.abort();
    setLoading(false);
    setPosition(null);
    setVillageName(null);
    setCoordinates({ lat: '', lng: '' });
    setAnalysis(null);
    setContourAnalysis(null);
    setContourFile(null);
    setError('');
    setFlyTarget(null);
    setStatus('Select a location, review the radius, then start the screening analysis.');
  };

  const contourColor = (elevation, minimum, maximum) => {
    const ratio = maximum > minimum ? (elevation - minimum) / (maximum - minimum) : 0.5;
    return `hsl(${260 - ratio * 55} 75% 66%)`;
  };

  return (
    <main className="app-container" aria-busy={loading}>
      <section className="map-container" aria-label="Satellite map and analysis layers">
        <MapContainer center={[20.5937, 78.9629]} zoom={5} style={{ height: '100%', width: '100%' }} keyboard>
          <TileLayer
            url={imageryTileUrl}
            attribution={imageryAttribution}
          />
          <FlyTo center={flyTarget} />
          <SelectionMarker position={position} onSelect={selectLocation} />
          {analysis?.catchment_polygon?.length >= 3 && (
            <Polygon positions={polygonPositions(analysis.catchment_polygon)} pathOptions={{ color: '#38bdf8', weight: 2, fillOpacity: 0.14 }}>
              <Tooltip sticky>Computed screening catchment</Tooltip>
            </Polygon>
          )}
          {contourAnalysis?.study_area_boundary?.length >= 3 && (
            <Polygon positions={polygonPositions(contourAnalysis.study_area_boundary)} pathOptions={{ color: '#fbbf24', weight: 2, fillOpacity: 0.04, dashArray: '7 5' }}>
              <Tooltip sticky>Uploaded contour study boundary</Tooltip>
            </Polygon>
          )}
          {contourAnalysis?.catchment?.boundary?.length >= 3 && (
            <Polygon positions={polygonPositions(contourAnalysis.catchment.boundary)} pathOptions={{ color: '#38bdf8', weight: 2, fillOpacity: 0.14 }}>
              <Tooltip sticky>Catchment derived from uploaded contours</Tooltip>
            </Polygon>
          )}
          {analysis?.contours?.map((contour, index) => (
            <Polyline
              key={`${contour.elevation}:${index}`}
              positions={polygonPositions(contour.points)}
              pathOptions={{
                color: contourColor(contour.elevation, analysis.elevation_stats.min_elevation, analysis.elevation_stats.max_elevation),
                weight: 1.4,
                opacity: 0.7,
                dashArray: '6 3',
              }}
            >
              <Tooltip sticky>{contour.elevation} m</Tooltip>
            </Polyline>
          ))}
          {analysis?.candidate_land_polygon?.length >= 3 && (
            <Polygon positions={polygonPositions(analysis.candidate_land_polygon)} pathOptions={{ color: '#fbbf24', weight: 2, fillOpacity: 0.1, dashArray: '5 5' }}>
              <Tooltip sticky>Detected bare-surface candidate; ownership and suitability unverified</Tooltip>
            </Polygon>
          )}
          {analysis?.pond && (
            <Marker position={[analysis.pond.lat, analysis.pond.lng]} icon={PondIcon}>
              <Popup>
                <strong>Screening candidate only</strong><br />
                Water depth: {analysis.pond.water_depth_m} m<br />
                Capacity: {numberOrDash(analysis.pond.capacity_m3, 0)} m³
              </Popup>
            </Marker>
          )}
          {contourAnalysis?.pond_location && (
            <Marker position={[contourAnalysis.pond_location.lat, contourAnalysis.pond_location.lng]} icon={PondIcon}>
              <Popup>
                <strong>Contour-derived candidate</strong><br />
                Elevation: {numberOrDash(contourAnalysis.pond_location.elevation_m, 2)} m<br />
                Catchment: {numberOrDash(contourAnalysis.catchment.area_hectares, 2)} ha
              </Popup>
            </Marker>
          )}
        </MapContainer>
        {(analysis || contourAnalysis) && <MapLegend mode={contourAnalysis ? 'contour' : 'location'} />}
      </section>

      <aside className="sidebar" aria-label="Pond screening controls and results">
        <header className="header">
          <p className="eyebrow">Decision-support prototype</p>
          <h1>Village pond screening</h1>
          <p>Terrain, rainfall and satellite evidence with explicit quality limits.</p>
        </header>

        <div className="screening-warning" role="note">
          Not a construction design or land-ownership determination. Field and qualified engineering verification are required.
        </div>

        <section className="contour-upload" aria-labelledby="contour-upload-heading">
          <p className="eyebrow">Phase 2 file workflow</p>
          <h2 id="contour-upload-heading">Analyze a contour map</h2>
          <p>Upload a KML or KMZ file containing at least three elevation levels. Results are computed from the uploaded geometry.</p>
          <form onSubmit={runContourAnalysis}>
            <label htmlFor="contour-file">Contour file</label>
            <input id="contour-file" type="file" accept=".kml,.kmz,application/vnd.google-earth.kml+xml,application/vnd.google-earth.kmz" onChange={selectContourFile} />
            <div className="file-hint">Maximum 15 MiB. KML and KMZ only.</div>
            <button className="btn" type="submit" disabled={!contourFile || loading}>Analyze contour map</button>
          </form>
        </section>

        <div className="workflow-divider"><span>or use live sources by location</span></div>

        <SearchBar onSelect={handleVillageSelect} />

        <form className="coordinate-form" onSubmit={submitCoordinates}>
          <fieldset>
            <legend>Or enter coordinates</legend>
            <label>Latitude<input type="number" step="0.000001" min="-85" max="85" value={coordinates.lat} onChange={(event) => setCoordinates({ ...coordinates, lat: event.target.value })} /></label>
            <label>Longitude<input type="number" step="0.000001" min="-180" max="180" value={coordinates.lng} onChange={(event) => setCoordinates({ ...coordinates, lng: event.target.value })} /></label>
          </fieldset>
          <button className="btn btn-secondary" type="submit">Select coordinates</button>
        </form>

        <div className="radius-control">
          <label htmlFor="radius-slider">Analysis radius: <strong>{radiusKm.toFixed(1)} km</strong></label>
          <input id="radius-slider" type="range" min="0.5" max="5" step="0.5" value={radiusKm} onChange={(event) => setRadiusKm(Number(event.target.value))} />
        </div>

        <div className="action-row">
          <button className="btn" type="button" disabled={!position || loading} onClick={runAnalysis}>Start screening analysis</button>
          {loading && <button className="btn btn-secondary" type="button" onClick={cancelAnalysis}>Cancel</button>}
        </div>

        <div className="sr-status" aria-live="polite" aria-atomic="true">{status}</div>
        {loading && <div className="loading-box" role="status"><span className="spinner" aria-hidden="true" /><span>Checking source coverage and computing the watershed…</span></div>}
        {error && <div className="error-box" role="alert"><p>{error}</p><button className="text-btn" type="button" onClick={contourFile && !position ? runContourAnalysis : runAnalysis}>Try again</button></div>}

        {contourAnalysis && (
          <div className="results">
            <section className={`quality-banner ${contourAnalysis.analysis_status}`}>
              <h2>Contour analysis: {contourAnalysis.analysis_status}</h2>
              <p>Screening-only result. The terrain surface is interpolated from the uploaded contour geometry.</p>
            </section>

            {contourAnalysis.quality.warnings.length > 0 && (
              <section className="warnings" aria-labelledby="contour-warning-heading">
                <h2 id="contour-warning-heading">Limitations and warnings</h2>
                <ul>{contourAnalysis.quality.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
              </section>
            )}

            <section aria-labelledby="contour-summary-heading">
              <h2 id="contour-summary-heading" className="section-label">Uploaded contour summary</h2>
              <dl className="stats-grid">
                <div><dt>Input file</dt><dd>{contourAnalysis.input_file}</dd></div>
                <div><dt>Format</dt><dd>{contourAnalysis.input_format.toUpperCase()}</dd></div>
                <div><dt>Contour lines</dt><dd>{numberOrDash(contourAnalysis.contour_summary.contour_count, 0)}</dd></div>
                <div><dt>Source vertices</dt><dd>{numberOrDash(contourAnalysis.contour_summary.source_point_count, 0)}</dd></div>
                <div><dt>Elevation levels</dt><dd>{numberOrDash(contourAnalysis.contour_summary.elevation_level_count, 0)}</dd></div>
                <div><dt>Elevation range</dt><dd>{numberOrDash(contourAnalysis.contour_summary.minimum_elevation_m, 2)} to {numberOrDash(contourAnalysis.contour_summary.maximum_elevation_m, 2)} m</dd></div>
                <div><dt>Median interval</dt><dd>{numberOrDash(contourAnalysis.contour_summary.median_contour_interval_m, 2)} m</dd></div>
                <div><dt>Grid</dt><dd>{contourAnalysis.grid.rows} x {contourAnalysis.grid.columns}</dd></div>
                <div><dt>Grid cell</dt><dd>{numberOrDash(contourAnalysis.grid.cell_size_m, 2)} m</dd></div>
                <div><dt>Observed cells</dt><dd>{(contourAnalysis.grid.observed_cell_ratio * 100).toFixed(2)}%</dd></div>
                <div><dt>Catchment</dt><dd>{numberOrDash(contourAnalysis.catchment.area_hectares, 4)} ha</dd></div>
                <div><dt>Study-grid share</dt><dd>{(contourAnalysis.catchment.study_grid_fraction * 100).toFixed(2)}%</dd></div>
              </dl>
            </section>

            <section className="pond-recommendation" aria-labelledby="contour-pond-heading">
              <h2 id="contour-pond-heading">Contour-derived pond candidate</h2>
              <dl>
                <div><dt>Point</dt><dd>{contourAnalysis.pond_location.lat.toFixed(6)}, {contourAnalysis.pond_location.lng.toFixed(6)}</dd></div>
                <div><dt>Elevation</dt><dd>{numberOrDash(contourAnalysis.pond_location.elevation_m, 3)} m</dd></div>
                <div><dt>Selection</dt><dd>{contourAnalysis.pond_location.selection_method}</dd></div>
                <div><dt>Interpolation</dt><dd>{contourAnalysis.grid.method}</dd></div>
              </dl>
            </section>

            <button className="btn btn-secondary" type="button" onClick={reset}>Reset analysis</button>
          </div>
        )}

        {analysis && (
          <div className="results">
            <section className={`quality-banner ${analysis.analysis_status}`}>
              <h2>Analysis status: {analysis.analysis_status}</h2>
              <p>{analysis.quality.screening_only ? 'Screening-only result. Do not use directly for excavation or construction.' : ''}</p>
            </section>

            {analysis.quality.warnings.length > 0 && (
              <section className="warnings" aria-labelledby="warning-heading">
                <h2 id="warning-heading">Limitations and warnings</h2>
                <ul>{analysis.quality.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
              </section>
            )}

            <section aria-labelledby="source-heading">
              <h2 id="source-heading" className="section-label">Source quality</h2>
              <div className="source-list">
                {Object.entries(analysis.quality.sources).map(([key, source]) => (
                  <details key={key}>
                    <summary><span>{source.name}</span><span className={`status-chip ${source.status}`}>{source.status}</span></summary>
                    <dl>
                      {source.resolution && <><dt>Resolution</dt><dd>{source.resolution}</dd></>}
                      {source.period && <><dt>Period</dt><dd>{source.period}</dd></>}
                      {source.model && <><dt>Model</dt><dd>{source.model}</dd></>}
                      <dt>Retrieved</dt><dd>{new Date(source.retrieved_at).toLocaleString()}</dd>
                      {source.message && <><dt>Note</dt><dd>{source.message}</dd></>}
                      {source.license_url && <><dt>Source terms</dt><dd><a href={source.license_url} target="_blank" rel="noreferrer">Open provider documentation</a></dd></>}
                    </dl>
                  </details>
                ))}
              </div>
            </section>

            <section aria-labelledby="terrain-heading">
              <h2 id="terrain-heading" className="section-label">Terrain and hydrology</h2>
              <dl className="stats-grid">
                <div><dt>Minimum elevation</dt><dd>{numberOrDash(analysis.elevation_stats.min_elevation)} m</dd></div>
                <div><dt>Maximum elevation</dt><dd>{numberOrDash(analysis.elevation_stats.max_elevation)} m</dd></div>
                <div><dt>Grid cell</dt><dd>{numberOrDash(analysis.elevation_stats.cell_size_m)} m</dd></div>
                <div><dt>Catchment</dt><dd>{numberOrDash(analysis.runoff_stats.catchment_area_sqm / 10000, 2)} ha</dd></div>
                <div><dt>Rainfall</dt><dd>{numberOrDash(analysis.rainfall_data.annual_avg_mm)} mm/year</dd></div>
                <div><dt>Runoff volume</dt><dd>{numberOrDash(analysis.runoff_stats.estimated_volume_m3, 0)} m³/year</dd></div>
                <div><dt>Runoff coefficient</dt><dd>{numberOrDash(analysis.runoff_stats.runoff_coefficient, 3)}</dd></div>
                <div><dt>Coefficient basis</dt><dd>{analysis.runoff_stats.runoff_coefficient_basis || 'Not configured'}</dd></div>
                <div><dt>Peak discharge</dt><dd>{analysis.runoff_stats.peak_discharge_m3_s == null ? 'Not configured' : `${numberOrDash(analysis.runoff_stats.peak_discharge_m3_s, 4)} m³/s`}</dd></div>
              </dl>
            </section>

            <section aria-labelledby="land-heading">
              <h2 id="land-heading" className="section-label">Satellite surface screening</h2>
              <dl className="stats-grid">
                <div><dt>Bare surface</dt><dd>{analysis.land_analysis.bare_surface_ratio == null ? 'Unavailable' : `${(analysis.land_analysis.bare_surface_ratio * 100).toFixed(1)}%`}</dd></div>
                <div><dt>Vegetation</dt><dd>{analysis.land_analysis.vegetation_ratio == null ? 'Unavailable' : `${(analysis.land_analysis.vegetation_ratio * 100).toFixed(1)}%`}</dd></div>
                <div><dt>Water</dt><dd>{analysis.land_analysis.water_ratio == null ? 'Unavailable' : `${(analysis.land_analysis.water_ratio * 100).toFixed(1)}%`}</dd></div>
                <div><dt>Candidate overlap</dt><dd>{numberOrDash(analysis.land_analysis.candidate_area_sqm, 0)} m²</dd></div>
              </dl>
            </section>

            <RainfallChart monthly={analysis.rainfall_data.monthly} />

            <section className="pond-recommendation" aria-labelledby="pond-heading">
              <h2 id="pond-heading">Pond screening result</h2>
              {analysis.pond ? (
                <dl>
                  <div><dt>Candidate point</dt><dd>{analysis.pond.lat.toFixed(5)}, {analysis.pond.lng.toFixed(5)}</dd></div>
                  <div><dt>Water / excavation depth</dt><dd>{analysis.pond.water_depth_m} / {analysis.pond.excavation_depth_m} m</dd></div>
                  <div><dt>Water dimensions</dt><dd>{analysis.pond.water_length_m} × {analysis.pond.water_width_m} m</dd></div>
                  <div><dt>Excavation crest dimensions</dt><dd>{analysis.pond.crest_length_m} × {analysis.pond.crest_width_m} m</dd></div>
                  <div><dt>Bottom dimensions</dt><dd>{analysis.pond.bottom_length_m} × {analysis.pond.bottom_width_m} m</dd></div>
                  <div><dt>Capacity</dt><dd>{numberOrDash(analysis.pond.capacity_m3, 0)} m³</dd></div>
                  <div><dt>Excavation volume</dt><dd>{numberOrDash(analysis.pond.excavation_volume_m3, 0)} m³</dd></div>
                  <div><dt>Excavation footprint</dt><dd>{numberOrDash(analysis.pond.excavation_footprint_area_sqm, 0)} m²</dd></div>
                  <div><dt>Side slope</dt><dd>{analysis.pond.side_slope_h_to_v}H:1V</dd></div>
                </dl>
              ) : <p>No pond candidate was produced because one or more required evidence gates failed.</p>}
            </section>

            <button className="btn btn-secondary" type="button" onClick={reset}>Reset analysis</button>
          </div>
        )}
      </aside>
    </main>
  );
}
