from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import pytest

from main import app
from services.contour_analyzer import (
    ContourFileError,
    analyze_contour_file,
    parse_contour_document,
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
    assert payload["analysis_status"] == "degraded"

    alias_response = await client.post("/api/analyzeContour", files=files)
    assert alias_response.status_code == 200


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
