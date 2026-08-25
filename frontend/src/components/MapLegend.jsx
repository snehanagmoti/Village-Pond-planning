export default function MapLegend({ mode = 'location' }) {
  return (
    <aside className="map-legend" aria-label="Map legend">
      <h2>Map legend</h2>
      <ul>
        <li><span className="legend-swatch catchment" aria-hidden="true" />Catchment screening boundary</li>
        {mode === 'location'
          ? <><li><span className="legend-swatch candidate" aria-hidden="true" />Detected bare-surface candidate</li><li><span className="legend-line" aria-hidden="true" />Elevation contours</li></>
          : <li><span className="legend-line study-area" aria-hidden="true" />Uploaded study boundary</li>}
        <li><span className="legend-dot pond" aria-hidden="true" />Candidate pond point</li>
        {mode === 'location' && <li><span className="legend-dot selected" aria-hidden="true" />Selected centre</li>}
      </ul>
    </aside>
  );
}
