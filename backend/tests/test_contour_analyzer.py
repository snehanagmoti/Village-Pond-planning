import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import numpy as np
import pytest

from main import app
from routers import pond_planner
from services.contour_analyzer import (
    ContourFileError,
    analyze_contour_file,
    parse_contour_document,
)
from services.cv_analyzer import SatelliteMosaic
from services.quality import SourceInfo, UpstreamDataError
from services.rainfall import RainfallResult


@pytest.fixture(autouse=True)
def contour_sources(monkeypatch):
    async def rainfall(_lat, _lng):
        return RainfallResult(
            annual_avg_mm=900.0,
            valid_years=30,
            monthly=[
                {"month": month, "rainfall_mm": 75.0, "valid_years": 30}
                for month in ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
            ],
            source=SourceInfo(name="test rainfall", status="reliable", period="1991-2020"),
        )

    async def imagery(lat, lng, radius):
        image = np.zeros((96, 96, 3), dtype=np.uint8)
        image[:, :48] = (55, 105, 155)
        image[:, 48:] = (75, 135, 185)
        offset = radius / 111.32
        return SatelliteMosaic(
            image=image,
            bounds=(lat - offset, lat + offset, lng - offset, lng + offset),
            zoom=14,
            source=SourceInfo(name="test imagery", status="reliable", resolution="10 m"),
        )

    monkeypatch.setattr(pond_planner, "get_rainfall_data", rainfall)
    monkeypatch.setattr(pond_planner, "download_satellite_mosaic", imagery)
    monkeypatch.setattr(pond_planner.settings, "approved_runoff_coefficient", 0.3)
    monkeypatch.setattr(
        pond_planner.settings,
        "approved_runoff_coefficient_source",
        "Test coefficient",
    )


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as session:
        yield session


def synthetic_kml() -> bytes:
    contour_lines = []
    # These are contours of a plane that rises to the north-east. The clipped
    # diagonal lines exercise interpolation and produce a convergent D8 basin.
    endpoints = (
        ((73.000, 18.002), (73.002, 18.000)),
        ((73.000, 18.006), (73.006, 18.000)),
        ((73.000, 18.010), (73.010, 18.000)),
        ((73.004, 18.010), (73.010, 18.004)),
        ((73.008, 18.010), (73.010, 18.008)),
    )
    for index, (start, end) in enumerate(endpoints):
        contour_lines.append(
            f"""
            <Placemark>
              <name>{100 + index}</name>
              <LineString><coordinates>
                {start[0]},{start[1]},0 {end[0]},{end[1]},0
              </coordinates></LineString>
            </Placemark>
            """
        )
    return (
        """<kml xmlns="http://www.opengis.net/kml/2.2"><Document>"""
        + "".join(contour_lines)
        + """
          <Placemark><name>study boundary</name><Polygon><outerBoundaryIs><LinearRing>
            <coordinates>
              73.0000,18.0000 73.0100,18.0000 73.0100,18.0100
              73.0000,18.0100 73.0000,18.0000
            </coordinates>
          </LinearRing></outerBoundaryIs></Polygon></Placemark>
        </Document></kml>"""
    ).encode()


def test_kml_analysis_derives_structured_catchment_without_hard_coded_site():
    result = analyze_contour_file(synthetic_kml(), "terrain.kml")

    assert result["input_format"] == "kml"
    assert result["contour_summary"] == {
        "contour_count": 5,
        "source_point_count": 10,
        "elevation_level_count": 5,
        "minimum_elevation_m": 100.0,
        "maximum_elevation_m": 104.0,
        "median_contour_interval_m": 1.0,
    }
    assert result["grid"]["rows"] >= 49
    assert result["grid"]["columns"] >= 49
    assert 18.0 <= result["pond_location"]["lat"] <= 18.01
    assert 73.0 <= result["pond_location"]["lng"] <= 73.01
    assert result["catchment"]["area_sqm"] > 0
    assert result["catchment"]["cell_count"] >= 3
    assert len(result["catchment"]["boundary"]) >= 3
    assert result["study_boundary_source"] == "uploaded_polygon"
    assert result["pond_location"]["boundary_distance_m"] >= result["candidate_boundary_setback_m"]
    assert result["pond_location"]["lat"] != result["outlet_location"]["lat"]
    assert len(result["contours"]) > 0
    assert len(result["drainage_path"]) >= 2
    assert result["quality"]["screening_only"] is True
    assert len(result["candidate_options"]) >= 1
    assert result["candidate_options"][0]["selected"] is True
    assert result["pond_location"]["contributing_area_sqm"] == pytest.approx(
        result["catchment"]["area_sqm"]
    )


def test_user_point_is_snapped_validated_and_used_as_the_catchment_pour_point():
    automatic = analyze_contour_file(synthetic_kml(), "terrain.kml")
    alternative = automatic["candidate_options"][-1]

    selected = analyze_contour_file(
        synthetic_kml(),
        "terrain.kml",
        selection_mode="point",
        selected_point={"lat": alternative["lat"], "lng": alternative["lng"]},
    )

    assert selected["selection"]["mode"] == "point"
    assert selected["candidate_options"][0]["selected"] is True
    assert selected["pond_location"]["lat"] == pytest.approx(alternative["lat"])
    assert selected["pond_location"]["contributing_area_sqm"] == pytest.approx(
        selected["catchment"]["area_sqm"]
    )


def test_user_region_limits_the_ranked_candidate_options():
    automatic = analyze_contour_file(synthetic_kml(), "terrain.kml")
    point = automatic["candidate_options"][0]
    delta = 0.0015
    region = [
        {"lat": point["lat"] - delta, "lng": point["lng"] - delta},
        {"lat": point["lat"] - delta, "lng": point["lng"] + delta},
        {"lat": point["lat"] + delta, "lng": point["lng"] + delta},
        {"lat": point["lat"] + delta, "lng": point["lng"] - delta},
    ]

    selected = analyze_contour_file(
        synthetic_kml(),
        "terrain.kml",
        selection_mode="region",
        selected_region=region,
    )

    assert selected["selection"]["mode"] == "region"
    assert all(
        region[0]["lat"] <= option["lat"] <= region[2]["lat"]
        and region[0]["lng"] <= option["lng"] <= region[1]["lng"]
        for option in selected["candidate_options"]
    )


def test_detected_water_buffer_rejects_a_user_selected_river_cell():
    automatic = analyze_contour_file(synthetic_kml(), "terrain.kml")
    point = automatic["candidate_options"][0]
    mask = np.zeros((101, 101), dtype=np.uint8)
    col = round((point["lng"] - 73.0) / 0.01 * 100)
    row = round((18.01 - point["lat"]) / 0.01 * 100)
    mask[max(0, row - 2):row + 3, max(0, col - 2):col + 3] = 255

    with pytest.raises(ContourFileError, match="detected-water exclusion buffer"):
        analyze_contour_file(
            synthetic_kml(),
            "terrain.kml",
            selection_mode="point",
            selected_point={"lat": point["lat"], "lng": point["lng"]},
            water_mask=mask,
            water_bounds=(18.0, 18.01, 73.0, 73.01),
        )


def test_kmz_uses_doc_kml_and_reports_archive_format():
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as kmz:
        kmz.writestr("ignored/readme.txt", "not a contour document")
        kmz.writestr("doc.kml", synthetic_kml())

    dataset, input_format = parse_contour_document(archive.getvalue(), "terrain.kmz")

    assert input_format == "kmz"
    assert len(dataset.lines) == 5
    assert len(dataset.boundary) == 5


def test_extended_data_value_is_used_when_placemark_name_is_not_numeric():
    placemarks = []
    for index in range(3):
        placemarks.append(
            f"""
            <Placemark><name>survey line</name><ExtendedData>
              <Data name="elevation"><value>{200 + index}</value></Data>
            </ExtendedData><LineString><coordinates>
              73,18.{index} 73.01,18.{index}
            </coordinates></LineString></Placemark>
            """
        )
    document = (
        "<kml><Document>" + "".join(placemarks) + "</Document></kml>"
    ).encode()

    dataset, _ = parse_contour_document(document, "survey.kml")

    assert [line.elevation for line in dataset.lines] == [200.0, 201.0, 202.0]


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (b"", "empty"),
        (b"<!DOCTYPE kml><kml/>", "DTD"),
        (
            b"<kml><Placemark><LineString><coordinates>73,18 74,19</coordinates>"
            b"</LineString></Placemark></kml>",
            "three contour lines",
        ),
        (b"<kml>", "well-formed"),
    ],
)
def test_invalid_or_unsafe_kml_is_rejected(document, message):
    with pytest.raises(ContourFileError, match=message):
        parse_contour_document(document, "terrain.kml")


@pytest.mark.anyio
async def test_contour_upload_api_and_assignment_alias(client):
    files = {
        "contour_file": (
            "terrain.kml",
            synthetic_kml(),
            "application/vnd.google-earth.kml+xml",
        )
    }
    response = await client.post("/api/analyze-contour", files=files)
    assert response.status_code == 200
    payload = response.json()
    assert payload["contour_summary"]["contour_count"] == 5
    assert payload["analysis_status"] == "complete"
    assert payload["dem_visualization"]["image_data_url"].startswith("data:image/png;base64,")
    assert payload["dem_visualization"]["maximum_elevation_m"] > payload["dem_visualization"]["minimum_elevation_m"]
    assert payload["rainfall_data"]["annual_avg_mm"] == 900.0
    assert payload["runoff_stats"]["estimated_volume_m3"] > 0
    assert payload["pond"]["capacity_m3"] > 0
    assert not any("comparative screening scores" in note for note in payload["quality"]["warnings"])
    assert not any("Annual runoff is a screening" in note for note in payload["quality"]["warnings"])
    assert not any("Peak discharge is unavailable" in note for note in payload["quality"]["warnings"])
    assert not any("Contour-workflow pond dimensions" in note for note in payload["quality"]["warnings"])
    assert payload["water_screening"]["status"] == "applied"

    alias_response = await client.post("/api/analyzeContour", files=files)
    assert alias_response.status_code == 200


@pytest.mark.anyio
async def test_contour_api_recomputes_for_manual_point_and_region(client):
    automatic = await client.post(
        "/api/analyze-contour",
        files={"contour_file": ("terrain.kml", synthetic_kml())},
    )
    assert automatic.status_code == 200
    alternative = automatic.json()["candidate_options"][-1]

    point_response = await client.post(
        "/api/analyze-contour",
        data={
            "selection_mode": "point",
            "selected_lat": str(alternative["lat"]),
            "selected_lng": str(alternative["lng"]),
        },
        files={"contour_file": ("terrain.kml", synthetic_kml())},
    )
    assert point_response.status_code == 200
    point_payload = point_response.json()
    assert point_payload["selection"]["mode"] == "point"
    assert point_payload["pond_location"]["lat"] == pytest.approx(alternative["lat"])
    assert point_payload["catchment"]["area_sqm"] == pytest.approx(
        point_payload["pond_location"]["contributing_area_sqm"], abs=0.01
    )

    delta = 0.0015
    region = [
        {"lat": alternative["lat"] - delta, "lng": alternative["lng"] - delta},
        {"lat": alternative["lat"] - delta, "lng": alternative["lng"] + delta},
        {"lat": alternative["lat"] + delta, "lng": alternative["lng"] + delta},
        {"lat": alternative["lat"] + delta, "lng": alternative["lng"] - delta},
    ]
    region_response = await client.post(
        "/api/analyze-contour",
        data={"selection_mode": "region", "selected_region": json.dumps(region)},
        files={"contour_file": ("terrain.kml", synthetic_kml())},
    )
    assert region_response.status_code == 200
    assert region_response.json()["selection"]["mode"] == "region"


@pytest.mark.anyio
async def test_contour_api_marks_missing_rainfall_outputs_incomplete(monkeypatch, client):
    async def unavailable(_lat, _lng):
        raise UpstreamDataError("rainfall", "Rainfall source unavailable in test")

    monkeypatch.setattr(pond_planner, "get_rainfall_data", unavailable)
    response = await client.post(
        "/api/analyze-contour",
        files={"contour_file": ("terrain.kml", synthetic_kml())},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_status"] == "incomplete"
    assert payload["rainfall_data"]["annual_avg_mm"] is None
    assert payload["runoff_stats"]["estimated_volume_m3"] is None
    assert payload["pond"] is None


@pytest.mark.anyio
async def test_contour_upload_api_rejects_wrong_form_field(client):
    response = await client.post(
        "/api/analyze-contour",
        files={"wrong_name": ("terrain.kml", synthetic_kml())},
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_contour_upload_rejects_oversized_body_before_parsing(client):
    response = await client.post(
        "/api/analyze-contour",
        content=b"",
        headers={"Content-Length": str(20 * 1024 * 1024)},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "contour_file_too_large"
