import { useEffect, useRef, useState } from 'react';
import {
  Circle,
  ImageOverlay,
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
const OutletIcon = L.divIcon({ html: '<span class="outlet-marker" aria-hidden="true"></span>', className: '', iconSize: [20, 20], iconAnchor: [10, 10] });
const candidateIcon = (rank, selected) => L.divIcon({
  html: `<span class="candidate-rank${selected ? ' selected' : ''}" aria-hidden="true">${Number(rank)}</span>`,
  className: '',
  iconSize: [28, 28],
  iconAnchor: [14, 14],
});
const imageryTileUrl = import.meta.env.VITE_IMAGERY_TILE_URL
  || 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const imageryAttribution = import.meta.env.VITE_IMAGERY_ATTRIBUTION
  || 'Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community';


function MapSelection({ position, onLocationSelect, onContourSelect, contourSelectionMode }) {
  useMapEvents({
    click(event) {
      const point = { lat: event.latlng.lat, lng: event.latlng.lng };
      if (contourSelectionMode === 'point' || contourSelectionMode === 'region') {
        onContourSelect(point);
      } else {
        onLocationSelect(point, null);
      }
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


function FitEvidence({ points, panelOpen }) {
  const map = useMap();
  const pointsKey = JSON.stringify(points.filter((point) => Array.isArray(point) && point.length === 2));
  useEffect(() => {
    const validPoints = JSON.parse(pointsKey);
    if (validPoints.length < 2) return undefined;
    const timer = window.setTimeout(() => {
      map.invalidateSize?.();
      const desktopPanelPadding = panelOpen && window.innerWidth > 760 ? 520 : 44;
      map.fitBounds(validPoints, {
        paddingTopLeft: [44, 72],
        paddingBottomRight: [desktopPanelPadding, 54],
        maxZoom: 15,
        animate: true,
      });
    }, 280);
    return () => window.clearTimeout(timer);
  }, [map, panelOpen, pointsKey]);
  return null;
}


const polygonPositions = (polygon = []) => polygon.map((point) => [point.lat, point.lng]);
const numberOrDash = (value, digits = 1) => value == null ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
const sourceStatusLabel = (status) => ({
  reliable: 'Ready',
  degraded: 'Public-data',
  unavailable: 'Unavailable',
})[status] || status;
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
  && ['complete', 'degraded', 'incomplete'].includes(value.analysis_status)
  && value.contour_summary
  && value.grid
  && value.pond_location
  && Array.isArray(value.candidate_options)
  && value.selection
  && value.catchment
  && value.rainfall_data
  && value.runoff_stats
  && value.water_screening
  && Array.isArray(value.catchment.boundary)
  && Array.isArray(value.study_area_boundary)
  && value.quality?.sources
  && Array.isArray(value.quality.warnings),
);


function TechnicalNotes({ warnings, label }) {
  const notes = [...new Set(warnings || [])];
  if (notes.length === 0) return null;
  return (
    <details className="technical-notes result-card">
      <summary><span>{label}</span><span className="note-count">{notes.length}</span></summary>
      <ul>{notes.map((warning) => <li key={warning}>{warning}</li>)}</ul>
    </details>
  );
}


export default function App() {
  const [panelOpen, setPanelOpen] = useState(true);
  const [workflowMode, setWorkflowMode] = useState('location');
  const [position, setPosition] = useState(null);
  const [villageName, setVillageName] = useState(null);
  const [coordinates, setCoordinates] = useState({ lat: '', lng: '' });
  const [radiusKm, setRadiusKm] = useState(2);
  const [analysis, setAnalysis] = useState(null);
  const [contourAnalysis, setContourAnalysis] = useState(null);
  const [contourFile, setContourFile] = useState(null);
  const [contourSelectionMode, setContourSelectionMode] = useState('automatic');
  const [contourPoint, setContourPoint] = useState(null);
  const [contourRegion, setContourRegion] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('Select a location, review the radius, then start the screening analysis.');
  const [flyTarget, setFlyTarget] = useState(null);
  const [visibleLayers, setVisibleLayers] = useState({
    catchment: true,
    contours: true,
    candidate: true,
    study: true,
    drainage: true,
    points: true,
  });
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
    setWorkflowMode('location');
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

  const handleContourMapClick = (point) => {
    if (workflowMode !== 'contour' || !contourAnalysis || loading) return;
    setError('');
    if (contourSelectionMode === 'point') {
      setContourPoint(point);
      setStatus(`Point selected at ${point.lat.toFixed(6)}, ${point.lng.toFixed(6)}. Press Evaluate selected point.`);
    } else if (contourSelectionMode === 'region') {
      setContourRegion((current) => current.length >= 100 ? current : [...current, point]);
      setStatus('Region vertex added. Add at least three vertices, then evaluate the search region.');
    }
  };

  const changeWorkflowMode = (mode) => {
    if (loading) return;
    setWorkflowMode(mode);
    setError('');
    if (analysis || contourAnalysis) return;
    if (mode === 'contour') {
      setStatus(contourFile
        ? `${contourFile.name} selected. Press Analyze contour map to upload and compute the catchment.`
        : 'Select a KML or KMZ contour map to start the file-based analysis.');
      return;
    }
    setStatus(position
      ? 'Location selected. Review the analysis radius and press Start screening analysis.'
      : 'Select a location, review the radius, then start the screening analysis.');
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
      setStatus(response.data.analysis_status === 'incomplete'
        ? 'Analysis finished, but one or more required evidence sources were unavailable.'
        : 'Analysis complete. Review the computed catchment, pond options and evidence sources.');
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
    setWorkflowMode('contour');
    setContourFile(file);
    setContourAnalysis(null);
    setContourSelectionMode('automatic');
    setContourPoint(null);
    setContourRegion([]);
    setError('');
    setStatus(file
      ? `${file.name} selected. Press Analyze contour map to upload and compute the catchment.`
      : 'Select a KML or KMZ contour map to start the file-based analysis.');
  };

  const runContourAnalysis = async (event, selectionOverride = null) => {
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
    const requestedMode = selectionOverride?.mode || contourSelectionMode;
    const requestedPoint = selectionOverride?.point || contourPoint;
    const requestedRegion = selectionOverride?.region || contourRegion;
    if (requestedMode === 'point' && !requestedPoint) {
      setError('Choose Select point, then click an eligible place inside the mapped study boundary.');
      return;
    }
    if (requestedMode === 'region' && requestedRegion.length < 3) {
      setError('Draw a search region with at least three map vertices before evaluating it.');
      return;
    }
    const body = new FormData();
    body.append('contour_file', contourFile);
    body.append('selection_mode', requestedMode);
    if (requestedMode === 'point') {
      body.append('selected_lat', String(requestedPoint.lat));
      body.append('selected_lng', String(requestedPoint.lng));
    }
    if (requestedMode === 'region') {
      body.append('selected_region', JSON.stringify(requestedRegion));
    }
    setLoading(true);
    setError('');
    setAnalysis(null);
    setStatus(requestedMode === 'automatic'
      ? 'Uploading contours, screening detected water and ranking candidate pond options.'
      : 'Re-evaluating the contours for the selected map point or search region.');
    try {
      const response = await api.post('/analyze-contour', body, { signal: controller.signal });
      if (sequence !== analysisSequenceRef.current) return;
      if (!hasContourContract(response.data)) {
        throw new Error('The API returned an unsupported contour-analysis contract.');
      }
      setContourAnalysis(response.data);
      setContourSelectionMode(response.data.selection.mode);
      setContourPoint(response.data.selection.requested_point || null);
      setContourRegion(response.data.selection.requested_region || []);
      setPosition(null);
      setVillageName(null);
      setCoordinates({ lat: '', lng: '' });
      setStatus('Contour analysis complete. Review the selected option and its computed catchment.');
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
    setContourSelectionMode('automatic');
    setContourPoint(null);
    setContourRegion([]);
    setError('');
    setFlyTarget(null);
    setStatus('Select a location, review the radius, then start the screening analysis.');
  };

  const contourColor = (elevation, minimum, maximum) => {
    const ratio = maximum > minimum ? (elevation - minimum) / (maximum - minimum) : 0.5;
    return `hsl(${260 - ratio * 55} 75% 66%)`;
  };

  const toggleLayer = (layer) => {
    setVisibleLayers((current) => ({ ...current, [layer]: !current[layer] }));
  };
  const chooseContourSelectionMode = (mode) => {
    if (loading) return;
    setContourSelectionMode(mode);
    setError('');
    if (mode === 'automatic') {
      setContourPoint(null);
      setContourRegion([]);
      setStatus('Automatic mode selected. Re-run to restore the highest-ranked terrain recommendation.');
    } else if (mode === 'point') {
      setContourRegion([]);
      setStatus('Point mode active. Click a point inside the uploaded study boundary, then evaluate it.');
    } else {
      setContourPoint(null);
      setContourRegion([]);
      setStatus('Region mode active. Click at least three vertices around the area to search.');
    }
  };
  const fitPoints = contourAnalysis?.study_area_boundary?.length >= 3
    ? polygonPositions(contourAnalysis.study_area_boundary)
    : analysis?.catchment_polygon?.length >= 3
      ? polygonPositions(analysis.catchment_polygon)
      : [];

  return (
    <main className={`app-container ${panelOpen ? '' : 'panel-collapsed'}`} aria-busy={loading}>
      <section className="map-container" aria-label="Satellite map and analysis layers">
        <div className="map-hud" aria-hidden="true">
          <span className="map-hud-kicker">Satellite intelligence workspace</span>
          <strong>{contourAnalysis ? 'Contour catchment model' : analysis ? 'Live watershed model' : position ? 'Study location selected' : 'India terrain overview'}</strong>
          <span>{contourAnalysis || analysis ? 'Model layers are ready for review' : 'Select a point on the map or use the analysis panel'}</span>
        </div>
        <MapContainer center={[20.5937, 78.9629]} zoom={5} style={{ height: '100%', width: '100%' }} keyboard>
          <TileLayer
            url={imageryTileUrl}
            attribution={imageryAttribution}
          />
          {visibleLayers.contours && contourAnalysis?.dem_visualization?.image_data_url && (
            <ImageOverlay
              url={contourAnalysis.dem_visualization.image_data_url}
              bounds={[
                [contourAnalysis.dem_visualization.south_west.lat, contourAnalysis.dem_visualization.south_west.lng],
                [contourAnalysis.dem_visualization.north_east.lat, contourAnalysis.dem_visualization.north_east.lng],
              ]}
              opacity={0.48}
              zIndex={220}
            />
          )}
          <FlyTo center={flyTarget} />
          <FitEvidence points={fitPoints} panelOpen={panelOpen} />
          <MapSelection
            position={position}
            onLocationSelect={selectLocation}
            onContourSelect={handleContourMapClick}
            contourSelectionMode={workflowMode === 'contour' && contourAnalysis ? contourSelectionMode : 'automatic'}
          />
          {position && visibleLayers.study && (
            <Circle
              center={[position.lat, position.lng]}
              radius={radiusKm * 1000}
              pathOptions={{ color: '#fbbf24', weight: 1.5, fillOpacity: 0.025, dashArray: '7 6' }}
            >
              <Tooltip sticky>{radiusKm} km live-analysis radius</Tooltip>
            </Circle>
          )}
          {visibleLayers.catchment && analysis?.catchment_polygon?.length >= 3 && (
            <Polygon positions={polygonPositions(analysis.catchment_polygon)} pathOptions={{ color: '#38bdf8', weight: 2, fillOpacity: 0.14 }}>
              <Tooltip sticky>Computed screening catchment</Tooltip>
            </Polygon>
          )}
          {visibleLayers.study && contourAnalysis?.study_area_boundary?.length >= 3 && (
            <Polygon positions={polygonPositions(contourAnalysis.study_area_boundary)} pathOptions={{ color: '#fbbf24', weight: 2, fillOpacity: 0.04, dashArray: '7 5' }}>
              <Tooltip sticky>{contourAnalysis.study_boundary_source === 'derived_extent' ? 'Derived contour-file extent' : 'Uploaded analysis extent (not verified suitable land)'}</Tooltip>
            </Polygon>
          )}
          {visibleLayers.catchment && contourAnalysis?.catchment?.boundary?.length >= 3 && (
            <Polygon positions={polygonPositions(contourAnalysis.catchment.boundary)} pathOptions={{ color: '#38bdf8', weight: 2, fillOpacity: 0.14 }}>
              <Tooltip sticky>Catchment derived from uploaded contours</Tooltip>
            </Polygon>
          )}
          {visibleLayers.contours && analysis?.contours?.map((contour, index) => (
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
          {visibleLayers.contours && contourAnalysis?.contours?.map((contour, index) => (
            <Polyline
              key={`uploaded:${contour.elevation}:${index}`}
              positions={polygonPositions(contour.points)}
              pathOptions={{
                color: contourColor(
                  contour.elevation,
                  contourAnalysis.contour_summary.minimum_elevation_m,
                  contourAnalysis.contour_summary.maximum_elevation_m,
                ),
                weight: 1.55,
                opacity: 0.82,
              }}
            >
              <Tooltip sticky>Reconstructed terrain contour · {contour.elevation} m</Tooltip>
            </Polyline>
          ))}
          {visibleLayers.candidate && analysis?.candidate_land_polygon?.length >= 3 && (
            <Polygon positions={polygonPositions(analysis.candidate_land_polygon)} pathOptions={{ color: '#fbbf24', weight: 2, fillOpacity: 0.1, dashArray: '5 5' }}>
              <Tooltip sticky>Detected bare-surface candidate; ownership and suitability unverified</Tooltip>
            </Polygon>
          )}
          {visibleLayers.drainage && contourAnalysis?.drainage_path?.length >= 2 && (
            <Polyline
              positions={polygonPositions(contourAnalysis.drainage_path)}
              pathOptions={{ color: '#ffb74d', weight: 3.2, opacity: 0.95, dashArray: '3 7' }}
            >
              <Tooltip sticky>Modelled D8 drainage path from the terrain candidate to the outlet</Tooltip>
            </Polyline>
          )}
          {workflowMode === 'contour' && contourSelectionMode === 'region' && contourRegion.length >= 3 && (
            <Polygon positions={polygonPositions(contourRegion)} pathOptions={{ color: '#c084fc', weight: 2.4, fillOpacity: 0.12, dashArray: '8 5' }}>
              <Tooltip sticky>User-drawn candidate search region</Tooltip>
            </Polygon>
          )}
          {workflowMode === 'contour' && contourSelectionMode === 'region' && contourRegion.length === 2 && (
            <Polyline positions={polygonPositions(contourRegion)} pathOptions={{ color: '#c084fc', weight: 2.4, dashArray: '8 5' }} />
          )}
          {workflowMode === 'contour' && contourPoint && contourSelectionMode === 'point' && (
            <Marker position={[contourPoint.lat, contourPoint.lng]}>
              <Popup><strong>Requested point</strong><br />This point will be snapped to and validated against the terrain grid.</Popup>
            </Marker>
          )}
          {visibleLayers.points && analysis?.pond && (
            <Marker position={[analysis.pond.lat, analysis.pond.lng]} icon={PondIcon}>
              <Popup>
                <strong>Screening candidate only</strong><br />
                Water depth: {analysis.pond.water_depth_m} m<br />
                Capacity: {numberOrDash(analysis.pond.capacity_m3, 0)} m³
              </Popup>
            </Marker>
          )}
          {visibleLayers.points && analysis?.candidate_options?.filter((option) => !option.selected).map((option) => (
            <Marker key={`live-option:${option.rank}:${option.lat}:${option.lng}`} position={[option.lat, option.lng]} icon={candidateIcon(option.rank, false)}>
              <Popup>
                <strong>Live-analysis alternative {option.rank}</strong><br />
                Suitability: {numberOrDash(option.suitability_score, 1)} / 100<br />
                Upstream area: {numberOrDash(option.contributing_area_hectares, 2)} ha<br />
                Local slope: {numberOrDash(option.local_slope_percent, 1)}%
              </Popup>
            </Marker>
          ))}
          {visibleLayers.points && contourAnalysis?.outlet_location && (
            <Marker position={[contourAnalysis.outlet_location.lat, contourAnalysis.outlet_location.lng]} icon={OutletIcon}>
              <Popup>
                <strong>Hydrologic outlet — not a pond recommendation</strong><br />
                Elevation: {numberOrDash(contourAnalysis.outlet_location.elevation_m, 2)} m<br />
                Contributing grid cells: {numberOrDash(contourAnalysis.outlet_location.contributing_cells, 0)}
              </Popup>
            </Marker>
          )}
          {visibleLayers.points && contourAnalysis?.candidate_options?.map((option) => (
            <Marker key={`candidate:${option.rank}:${option.lat}:${option.lng}`} position={[option.lat, option.lng]} icon={candidateIcon(option.rank, option.selected)}>
              <Popup>
                <strong>{option.selected ? 'Selected pond candidate' : `Candidate option ${option.rank}`}</strong><br />
                Suitability: {numberOrDash(option.suitability_score, 1)} / 100<br />
                Contributing area: {numberOrDash(option.contributing_area_hectares, 2)} ha<br />
                Local slope: {numberOrDash(option.local_slope_percent, 1)}%<br />
                Water clearance: {option.water_distance_m == null ? 'Not available' : `${numberOrDash(option.water_distance_m, 0)} m`}
              </Popup>
            </Marker>
          ))}
        </MapContainer>
        {(analysis || contourAnalysis) && (
          <MapLegend
            mode={contourAnalysis ? 'contour' : 'location'}
            layers={visibleLayers}
            onToggle={toggleLayer}
            studyBoundarySource={contourAnalysis?.study_boundary_source}
            minimumElevation={contourAnalysis?.contour_summary?.minimum_elevation_m ?? analysis?.elevation_stats?.min_elevation}
            maximumElevation={contourAnalysis?.contour_summary?.maximum_elevation_m ?? analysis?.elevation_stats?.max_elevation}
          />
        )}
        <div className="map-mode-chip" aria-hidden="true">
          <span className="live-dot" />
          {loading ? 'Model processing' : analysis || contourAnalysis ? 'Evidence layers active' : 'Map ready'}
        </div>
      </section>

      <button
        className="panel-toggle"
        type="button"
        aria-controls="analysis-panel"
        aria-expanded={panelOpen}
        onClick={() => setPanelOpen((open) => !open)}
      >
        <span aria-hidden="true">{panelOpen ? '›' : '‹'}</span>
        {panelOpen ? 'Hide panel' : 'Show panel'}
      </button>

      <aside
        id="analysis-panel"
        className={`sidebar ${panelOpen ? '' : 'is-collapsed'}`}
        aria-label="Pond screening controls and results"
        aria-hidden={!panelOpen}
        inert={!panelOpen}
      >
        <header className="header">
          <div className="brand-row">
            <div className="brand-mark" aria-hidden="true">
              <svg viewBox="0 0 44 44">
                <path d="M22 5.5c7.2 9.2 11.2 14.8 11.2 21a11.2 11.2 0 0 1-22.4 0c0-6.2 4-11.8 11.2-21Z" />
                <path d="M13.5 27.5c4.7-2.7 12.3-2.7 17 0M15.8 32c3.6-1.8 8.8-1.8 12.4 0" />
              </svg>
            </div>
            <div>
              <p className="eyebrow">Village Pond Intelligence</p>
              <p className="brand-name">JalDrishti</p>
            </div>
            <span className="prototype-chip">Course project</span>
          </div>
          <h1>Plan with the landscape, not against it.</h1>
          <p>Combine terrain, rainfall and satellite evidence into an explainable pond screening model.</p>
        </header>

        <div className="project-note" role="note">
          <span className="note-symbol" aria-hidden="true">i</span>
          <span><strong>Course-project model.</strong> Validate the selected site locally before construction.</span>
        </div>

        <div className="workflow-switcher" role="tablist" aria-label="Analysis workflow">
          <button
            className={workflowMode === 'location' ? 'active' : ''}
            type="button"
            role="tab"
            aria-label="Live analysis"
            aria-selected={workflowMode === 'location'}
            aria-controls="location-workflow"
            disabled={loading}
            onClick={() => changeWorkflowMode('location')}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s6-5.1 6-11a6 6 0 1 0-12 0c0 5.9 6 11 6 11Z" /><circle cx="12" cy="10" r="2.3" /></svg>
            <span><strong>Live analysis</strong><small>Search or coordinates</small></span>
          </button>
          <button
            className={workflowMode === 'contour' ? 'active' : ''}
            type="button"
            role="tab"
            aria-label="Contour upload"
            aria-selected={workflowMode === 'contour'}
            aria-controls="contour-workflow"
            disabled={loading}
            onClick={() => changeWorkflowMode('contour')}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 7 6-3 6 3 6-3v13l-6 3-6-3-6 3V7Z" /><path d="M9 4v13M15 7v13" /></svg>
            <span><strong>Contour upload</strong><small>KML or KMZ terrain</small></span>
          </button>
        </div>

        {workflowMode === 'contour' ? (
          <section id="contour-workflow" className="workflow-panel contour-upload" role="tabpanel" aria-labelledby="contour-upload-heading">
            <div className="workflow-heading">
              <span className="step-number">01</span>
              <div><p className="eyebrow">File-based terrain model</p><h2 id="contour-upload-heading">Analyze a contour map</h2></div>
            </div>
            <p>Upload surveyed contour geometry to reconstruct a terrain surface and derive its contributing catchment.</p>
            <form onSubmit={runContourAnalysis}>
              <label htmlFor="contour-file">Contour file</label>
              <div className="file-dropzone">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v5h14v-5" /></svg>
                <input id="contour-file" type="file" accept=".kml,.kmz,application/vnd.google-earth.kml+xml,application/vnd.google-earth.kmz" onChange={selectContourFile} />
              </div>
              <div className="file-meta"><span>KML / KMZ</span><span>Maximum 15 MiB</span><span>3+ elevation levels</span></div>
              <button className="btn" type="submit" disabled={!contourFile || loading}>
                <span>Analyze contour map</span><span aria-hidden="true">→</span>
              </button>
            </form>
          </section>
        ) : (
          <section id="location-workflow" className="workflow-panel location-workflow" role="tabpanel" aria-labelledby="location-workflow-heading">
            <div className="workflow-heading">
              <span className="step-number">01</span>
              <div><p className="eyebrow">Live-source screening</p><h2 id="location-workflow-heading">Choose a study area</h2></div>
            </div>
            <SearchBar onSelect={handleVillageSelect} />

            <div className="workflow-divider"><span>or enter coordinates</span></div>

            <form className="coordinate-form" onSubmit={submitCoordinates}>
              <fieldset>
                <legend>Or enter coordinates</legend>
                <label>Latitude<input type="number" step="0.000001" min="-85" max="85" placeholder="20.5937" value={coordinates.lat} onChange={(event) => setCoordinates({ ...coordinates, lat: event.target.value })} /></label>
                <label>Longitude<input type="number" step="0.000001" min="-180" max="180" placeholder="78.9629" value={coordinates.lng} onChange={(event) => setCoordinates({ ...coordinates, lng: event.target.value })} /></label>
              </fieldset>
              <button className="btn btn-secondary" type="submit">Select coordinates</button>
            </form>

            <div className="radius-control">
              <div className="radius-heading"><label htmlFor="radius-slider">Analysis radius</label><strong>{radiusKm.toFixed(1)} km</strong></div>
              <input id="radius-slider" aria-label={`Analysis radius: ${radiusKm.toFixed(1)} km`} type="range" min="0.5" max="5" step="0.5" value={radiusKm} onChange={(event) => setRadiusKm(Number(event.target.value))} />
              <div className="radius-scale" aria-hidden="true"><span>0.5 km</span><span>Focused village study</span><span>5 km</span></div>
            </div>

            <div className="action-row">
              <button className="btn" type="button" disabled={!position || loading} onClick={runAnalysis}>
                <span>Start screening analysis</span><span aria-hidden="true">→</span>
              </button>
              {loading && <button className="btn btn-secondary" type="button" onClick={cancelAnalysis}>Cancel</button>}
            </div>
          </section>
        )}

        <div className="status-console" aria-live="polite" aria-atomic="true">
          <span className={`status-indicator ${loading ? 'processing' : error ? 'error' : analysis || contourAnalysis ? 'complete' : ''}`} aria-hidden="true" />
          <div><span className="status-label">Workspace status</span><p>{status}</p></div>
        </div>
        {loading && (
          <div className="loading-box" role="status">
            <span className="spinner" aria-hidden="true" />
            <span>{workflowMode === 'contour'
              ? 'Reconstructing the terrain and catchment… Large contour files may take up to five minutes.'
              : 'Checking source coverage and computing the watershed…'}</span>
          </div>
        )}
        {error && <div className="error-box" role="alert"><p>{error}</p><button className="text-btn" type="button" onClick={contourFile && !position ? runContourAnalysis : runAnalysis}>Try again</button></div>}

        {contourAnalysis && (
          <div className="results">
            <div className="results-heading">
              <div><p className="eyebrow">Computed evidence</p><h2>Contour screening report</h2><p>Review the model output, quality limits and mapped catchment.</p></div>
              <button className="icon-btn" type="button" onClick={reset} aria-label="Reset analysis">↺</button>
            </div>
            <section className={`quality-banner ${contourAnalysis.analysis_status === 'incomplete' ? 'incomplete' : 'complete'}`}>
              <h2>{contourAnalysis.analysis_status === 'incomplete' ? 'Contour analysis incomplete' : 'Contour analysis complete'}</h2>
              <p>Catchment and pond options were computed from the uploaded contour elevations.</p>
            </section>

            <section className="result-card contour-selection-tools" aria-labelledby="contour-selection-heading">
              <p className="eyebrow">Interactive siting</p>
              <h2 id="contour-selection-heading">Choose how the pond point is selected</h2>
              <p>The server always re-checks the study boundary, outlet, contributing flow and detected-water buffer. A map click never bypasses those safeguards.</p>
              <div className="selection-mode-grid" role="group" aria-label="Contour candidate selection mode">
                <button type="button" aria-pressed={contourSelectionMode === 'automatic'} onClick={() => chooseContourSelectionMode('automatic')}>
                  <strong>Automatic</strong><span>Best ranked option</span>
                </button>
                <button type="button" aria-pressed={contourSelectionMode === 'point'} onClick={() => chooseContourSelectionMode('point')}>
                  <strong>Select point</strong><span>Click one place</span>
                </button>
                <button type="button" aria-pressed={contourSelectionMode === 'region'} onClick={() => chooseContourSelectionMode('region')}>
                  <strong>Draw region</strong><span>Search inside polygon</span>
                </button>
              </div>
              {contourSelectionMode === 'point' && (
                <div className="selection-action">
                  <p>{contourPoint ? `Requested point: ${contourPoint.lat.toFixed(6)}, ${contourPoint.lng.toFixed(6)}` : 'Click the map to place the requested point.'}</p>
                  <button className="btn" type="button" disabled={!contourPoint || loading} onClick={() => runContourAnalysis(null, { mode: 'point', point: contourPoint })}>Evaluate selected point</button>
                </div>
              )}
              {contourSelectionMode === 'region' && (
                <div className="selection-action">
                  <p>{contourRegion.length} vertices placed. Use at least 3; the final vertex connects back to the first.</p>
                  <div className="compact-actions">
                    <button className="btn btn-secondary" type="button" disabled={!contourRegion.length || loading} onClick={() => setContourRegion((current) => current.slice(0, -1))}>Undo vertex</button>
                    <button className="btn btn-secondary" type="button" disabled={!contourRegion.length || loading} onClick={() => setContourRegion([])}>Clear</button>
                    <button className="btn" type="button" disabled={contourRegion.length < 3 || loading} onClick={() => runContourAnalysis(null, { mode: 'region', region: contourRegion })}>Evaluate region</button>
                  </div>
                </div>
              )}
              {contourSelectionMode === 'automatic' && contourAnalysis.selection.mode !== 'automatic' && (
                <button className="btn" type="button" disabled={loading} onClick={() => runContourAnalysis(null, { mode: 'automatic' })}>Restore automatic recommendation</button>
              )}
            </section>

            <TechnicalNotes warnings={contourAnalysis.quality.warnings} label="Contour data notes" />

            <section className="result-card" aria-labelledby="contour-summary-heading">
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

            <section className="result-card" aria-labelledby="contour-water-heading">
              <h2 id="contour-water-heading" className="section-label">River and water safeguard</h2>
              <dl className="stats-grid">
                <div><dt>Status</dt><dd>{contourAnalysis.water_screening.status}</dd></div>
                <div><dt>Detected water</dt><dd>{contourAnalysis.water_screening.detected_water_ratio == null ? 'Unavailable' : `${(contourAnalysis.water_screening.detected_water_ratio * 100).toFixed(2)}%`}</dd></div>
                <div><dt>Hard exclusion buffer</dt><dd>{numberOrDash(contourAnalysis.water_screening.exclusion_buffer_m, 0)} m</dd></div>
                <div><dt>Method</dt><dd>{contourAnalysis.water_screening.method}</dd></div>
              </dl>
              <p className="card-note">{contourAnalysis.water_screening.message}</p>
            </section>

            <section className="result-card" aria-labelledby="contour-options-heading">
              <h2 id="contour-options-heading" className="section-label">Pond location options</h2>
              <p>Options are spatially separated and ranked from the same terrain evidence. Select any option to recompute its catchment and pond geometry.</p>
              <div className="candidate-option-list">
                {contourAnalysis.candidate_options.map((option) => (
                  <article key={`${option.rank}:${option.lat}:${option.lng}`} className={option.selected ? 'selected' : ''}>
                    <div className="candidate-option-heading"><strong>Option {option.rank}</strong><span>{numberOrDash(option.suitability_score, 1)} / 100</span></div>
                    <p>{option.lat.toFixed(6)}, {option.lng.toFixed(6)}</p>
                    <dl>
                      <div><dt>Upstream area</dt><dd>{numberOrDash(option.contributing_area_hectares, 2)} ha</dd></div>
                      <div><dt>Local slope</dt><dd>{numberOrDash(option.local_slope_percent, 1)}%</dd></div>
                      <div><dt>Boundary clearance</dt><dd>{numberOrDash(option.boundary_distance_m, 0)} m</dd></div>
                      <div><dt>Water clearance</dt><dd>{option.water_distance_m == null ? 'Unavailable' : `${numberOrDash(option.water_distance_m, 0)} m`}</dd></div>
                    </dl>
                    {option.selected
                      ? <span className="selected-option-label">Selected for this result</span>
                      : <button className="text-btn" type="button" disabled={loading} onClick={() => runContourAnalysis(null, { mode: 'point', point: option })}>Use this option and recompute</button>}
                  </article>
                ))}
              </div>
            </section>

            <section className="pond-recommendation result-card" aria-labelledby="contour-pond-heading">
              <h2 id="contour-pond-heading">Selected pond screening result</h2>
              <dl>
                <div><dt>Point</dt><dd>{contourAnalysis.pond_location.lat.toFixed(6)}, {contourAnalysis.pond_location.lng.toFixed(6)}</dd></div>
                <div><dt>Elevation</dt><dd>{numberOrDash(contourAnalysis.pond_location.elevation_m, 3)} m</dd></div>
                <div><dt>Boundary setback</dt><dd>{numberOrDash(contourAnalysis.pond_location.boundary_distance_m, 0)} m</dd></div>
                <div><dt>Local slope</dt><dd>{numberOrDash(contourAnalysis.pond_location.local_slope_percent, 2)}%</dd></div>
                <div><dt>Suitability score</dt><dd>{numberOrDash(contourAnalysis.pond_location.suitability_score, 1)} / 100</dd></div>
                <div><dt>Selection</dt><dd>{contourAnalysis.pond_location.selection_method}</dd></div>
                <div><dt>Interpolation</dt><dd>{contourAnalysis.grid.method}</dd></div>
              </dl>
            </section>

            <section className="result-card" aria-labelledby="contour-hydrology-heading">
              <h2 id="contour-hydrology-heading" className="section-label">Rainfall, catchment and runoff</h2>
              <dl className="stats-grid">
                <div><dt>Catchment area</dt><dd>{numberOrDash(contourAnalysis.catchment.area_hectares, 3)} ha</dd></div>
                <div><dt>Annual rainfall</dt><dd>{numberOrDash(contourAnalysis.rainfall_data.annual_avg_mm, 1)} mm/year</dd></div>
                <div><dt>Valid rainfall years</dt><dd>{numberOrDash(contourAnalysis.rainfall_data.valid_years, 0)}</dd></div>
                <div><dt>Estimated runoff volume</dt><dd>{numberOrDash(contourAnalysis.runoff_stats.estimated_volume_m3, 0)} m³/year</dd></div>
                <div><dt>Runoff coefficient</dt><dd>{numberOrDash(contourAnalysis.runoff_stats.runoff_coefficient, 3)}</dd></div>
                <div><dt>Coefficient basis</dt><dd>{contourAnalysis.runoff_stats.runoff_coefficient_basis || 'Not configured'}</dd></div>
              </dl>
            </section>

            <RainfallChart monthly={contourAnalysis.rainfall_data.monthly} />

            <section className="pond-recommendation result-card" aria-labelledby="contour-geometry-heading">
              <h2 id="contour-geometry-heading">Recommended preliminary pond geometry</h2>
              {contourAnalysis.pond ? (
                <dl>
                  <div><dt>Water / excavation depth</dt><dd>{contourAnalysis.pond.water_depth_m} / {contourAnalysis.pond.excavation_depth_m} m</dd></div>
                  <div><dt>Water dimensions</dt><dd>{contourAnalysis.pond.water_length_m} × {contourAnalysis.pond.water_width_m} m</dd></div>
                  <div><dt>Crest dimensions</dt><dd>{contourAnalysis.pond.crest_length_m} × {contourAnalysis.pond.crest_width_m} m</dd></div>
                  <div><dt>Bottom dimensions</dt><dd>{contourAnalysis.pond.bottom_length_m} × {contourAnalysis.pond.bottom_width_m} m</dd></div>
                  <div><dt>Storage capacity</dt><dd>{numberOrDash(contourAnalysis.pond.capacity_m3, 0)} m³</dd></div>
                  <div><dt>Excavation volume</dt><dd>{numberOrDash(contourAnalysis.pond.excavation_volume_m3, 0)} m³</dd></div>
                  <div><dt>Excavation footprint</dt><dd>{numberOrDash(contourAnalysis.pond.excavation_footprint_area_sqm, 0)} m²</dd></div>
                  <div><dt>Side slope</dt><dd>{contourAnalysis.pond.side_slope_h_to_v}H:1V</dd></div>
                </dl>
              ) : <p>Pond dimensions are unavailable because rainfall or an approved runoff coefficient is missing.</p>}
            </section>

            <section className="result-card" aria-labelledby="contour-sources-heading">
              <h2 id="contour-sources-heading" className="section-label">Evidence sources</h2>
              <div className="source-list">
                {Object.entries(contourAnalysis.quality.sources).map(([key, source]) => (
                  <details key={key}>
                    <summary><span>{source.name}</span><span className={`status-chip ${source.status}`}>{sourceStatusLabel(source.status)}</span></summary>
                    <dl>
                      {source.resolution && <><dt>Resolution</dt><dd>{source.resolution}</dd></>}
                      {source.period && <><dt>Period</dt><dd>{source.period}</dd></>}
                      {source.model && <><dt>Model</dt><dd>{source.model}</dd></>}
                      <dt>Retrieved</dt><dd>{new Date(source.retrieved_at).toLocaleString()}</dd>
                      {source.message && <><dt>Note</dt><dd>{source.message}</dd></>}
                    </dl>
                  </details>
                ))}
              </div>
            </section>

          </div>
        )}

        {analysis && (
          <div className="results">
            <div className="results-heading">
              <div><p className="eyebrow">Computed evidence</p><h2>Watershed screening report</h2><p>Source-aware terrain, runoff and candidate geometry in one review.</p></div>
              <button className="icon-btn" type="button" onClick={reset} aria-label="Reset analysis">↺</button>
            </div>
            <section className={`quality-banner ${analysis.analysis_status}`}>
              <h2>{analysis.analysis_status === 'complete'
                ? 'Analysis complete'
                : analysis.analysis_status === 'degraded'
                  ? 'Analysis complete with public-data constraints'
                  : 'Analysis incomplete'}</h2>
              <p>{analysis.analysis_status === 'incomplete'
                ? 'A required evidence source or calculation gate was unavailable.'
                : 'Core calculations completed. Open the technical notes for source-resolution details.'}</p>
            </section>

            <TechnicalNotes warnings={analysis.quality.warnings} label="Technical notes" />

            <section className="result-card" aria-labelledby="source-heading">
              <h2 id="source-heading" className="section-label">Source quality</h2>
              <div className="source-list">
                {Object.entries(analysis.quality.sources).map(([key, source]) => (
                  <details key={key}>
                    <summary><span>{source.name}</span><span className={`status-chip ${source.status}`}>{sourceStatusLabel(source.status)}</span></summary>
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

            <section className="result-card" aria-labelledby="terrain-heading">
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

            <section className="result-card" aria-labelledby="land-heading">
              <h2 id="land-heading" className="section-label">Satellite surface screening</h2>
              <dl className="stats-grid">
                <div><dt>Bare surface</dt><dd>{analysis.land_analysis.bare_surface_ratio == null ? 'Unavailable' : `${(analysis.land_analysis.bare_surface_ratio * 100).toFixed(1)}%`}</dd></div>
                <div><dt>Vegetation</dt><dd>{analysis.land_analysis.vegetation_ratio == null ? 'Unavailable' : `${(analysis.land_analysis.vegetation_ratio * 100).toFixed(1)}%`}</dd></div>
                <div><dt>Water</dt><dd>{analysis.land_analysis.water_ratio == null ? 'Unavailable' : `${(analysis.land_analysis.water_ratio * 100).toFixed(1)}%`}</dd></div>
                <div><dt>Candidate overlap</dt><dd>{numberOrDash(analysis.land_analysis.candidate_area_sqm, 0)} m²</dd></div>
              </dl>
            </section>

            <RainfallChart monthly={analysis.rainfall_data.monthly} />

            {analysis.candidate_options?.length > 0 && (
              <section className="result-card" aria-labelledby="live-options-heading">
                <h2 id="live-options-heading" className="section-label">Ranked pond location options</h2>
                <div className="candidate-option-list">
                  {analysis.candidate_options.map((option) => (
                    <article key={`live:${option.rank}:${option.lat}:${option.lng}`} className={option.selected ? 'selected' : ''}>
                      <div className="candidate-option-heading"><strong>Option {option.rank}</strong><span>{numberOrDash(option.suitability_score, 1)} / 100</span></div>
                      <p>{option.lat.toFixed(6)}, {option.lng.toFixed(6)}</p>
                      <dl>
                        <div><dt>Upstream area</dt><dd>{numberOrDash(option.contributing_area_hectares, 2)} ha</dd></div>
                        <div><dt>Local slope</dt><dd>{numberOrDash(option.local_slope_percent, 1)}%</dd></div>
                        <div><dt>Water clearance</dt><dd>{option.water_distance_m == null ? 'Unavailable' : `${numberOrDash(option.water_distance_m, 0)} m`}</dd></div>
                      </dl>
                      {option.selected && <span className="selected-option-label">Used for this result</span>}
                    </article>
                  ))}
                </div>
              </section>
            )}

            <section className="pond-recommendation result-card" aria-labelledby="pond-heading">
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

          </div>
        )}
      </aside>
    </main>
  );
}
