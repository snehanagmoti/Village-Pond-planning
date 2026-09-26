const fmt = (value, digits = 0) => Number.isFinite(value)
  ? value.toLocaleString('en-US', { maximumFractionDigits: digits }) : 'Unavailable';

export default function MapResultSummary({ result, contour = false }) {
  if (!result) return null;
  const area = contour ? result.catchment?.area_sqm : result.runoff_stats?.catchment_area_sqm;
  const location = result.pond || (contour ? result.pond_location : null);
  return (
    <section className="map-result-summary" aria-label="Mapped analysis results">
      <strong>Selected catchment & water estimate</strong>
      <dl>
        <div><dt>Catchment</dt><dd>{fmt(area == null ? null : area / 10000, 2)} ha</dd></div>
        <div><dt>Expected annual runoff</dt><dd>{fmt(result.runoff_stats?.estimated_volume_m3)} m³/year</dd></div>
        <div><dt>Pond storage capacity</dt><dd>{fmt(result.pond?.capacity_m3)} m³</dd></div>
      </dl>
      <p>{location ? `Pond: ${fmt(location.lat, 5)}, ${fmt(location.lng, 5)}` : 'No valid pond recommendation'}</p>
      <small>Annual inflow estimate is not storage capacity.</small>
    </section>
  );
}
