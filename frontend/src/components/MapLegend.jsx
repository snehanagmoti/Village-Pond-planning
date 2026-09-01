const LayerToggle = ({ layer, enabled, onToggle, swatchClass, children }) => (
  <li>
    <button
      className="map-layer-toggle"
      type="button"
      aria-pressed={enabled}
      onClick={() => onToggle(layer)}
    >
      <span className={swatchClass} aria-hidden="true" />
      <span>{children}</span>
    </button>
  </li>
);


export default function MapLegend({
  mode = 'location',
  layers,
  onToggle,
  studyBoundarySource,
  minimumElevation,
  maximumElevation,
}) {
  const extentLabel = studyBoundarySource === 'derived_extent'
    ? 'Derived contour-file extent'
    : mode === 'contour'
      ? 'Uploaded analysis extent'
      : 'Selected study radius';

  return (
    <aside className="map-legend" aria-label="Interactive map layers">
      <div className="map-legend-heading">
        <div><p>Map layers</p><span>Click to show or hide</span></div>
        <strong>{mode === 'contour' ? 'Contour model' : 'Live model'}</strong>
      </div>
      <ul>
        <LayerToggle layer="catchment" enabled={layers.catchment} onToggle={onToggle} swatchClass="legend-swatch catchment">
          Catchment boundary
        </LayerToggle>
        <LayerToggle layer="contours" enabled={layers.contours} onToggle={onToggle} swatchClass="legend-line terrain">
          {mode === 'contour' ? 'DEM surface + elevation contours' : 'Reconstructed elevation contours'}
        </LayerToggle>
        <LayerToggle layer="study" enabled={layers.study} onToggle={onToggle} swatchClass="legend-line study-area">
          {extentLabel}
        </LayerToggle>
        {mode === 'location' && (
          <LayerToggle layer="candidate" enabled={layers.candidate} onToggle={onToggle} swatchClass="legend-swatch candidate">
            RGB/HSV land candidate
          </LayerToggle>
        )}
        {mode === 'contour' && (
          <LayerToggle layer="drainage" enabled={layers.drainage} onToggle={onToggle} swatchClass="legend-line drainage">
            Modelled drainage path
          </LayerToggle>
        )}
        <LayerToggle layer="points" enabled={layers.points} onToggle={onToggle} swatchClass="legend-dot pond">
          {mode === 'contour' ? 'Ranked pond options + outlet' : 'Selected centre + pond options'}
        </LayerToggle>
      </ul>
      {minimumElevation != null && maximumElevation != null && (
        <div className="elevation-ramp" aria-label={`Elevation range ${minimumElevation} to ${maximumElevation} metres`}>
          <span>{minimumElevation} m</span><i aria-hidden="true" /><span>{maximumElevation} m</span>
        </div>
      )}
      {mode === 'contour' && (
        <p className="legend-note">
          The colour surface shows terrain elevation—not water. The orange outlet is hydrology evidence, not a pond recommendation.
        </p>
      )}
    </aside>
  );
}
