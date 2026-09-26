"""Bounded real-API concurrency and numerical checks. Run on the allotted host.

Usage: python verify_submission.py --base http://127.0.0.1:3000 --kml ../contours_1m.kml
Does not fabricate source data or claim field-survey validation.
"""
import argparse
import asyncio
import json
import time
from pathlib import Path
import httpx


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:3000')
    parser.add_argument('--kml', type=Path, required=True)
    parser.add_argument('--selections-only', action='store_true')
    args = parser.parse_args()
    content = args.kml.read_bytes()
    async with httpx.AsyncClient(base_url=args.base, timeout=240, trust_env=False) as client:
        async def upload(index):
            start = time.monotonic()
            response = await client.post('/api/analyze-contour', files={'contour_map': ('contours_1m.kml', content)})
            response.raise_for_status()
            data = response.json()
            assert data['analysis_status'] == 'complete', data.get('quality')
            stats = data['runoff_stats']
            expected = stats['catchment_area_sqm'] * stats['annual_rainfall_mm'] / 1000 * stats['runoff_coefficient']
            assert abs(expected - stats['estimated_volume_m3']) < max(1, expected * .0001)
            assert data['pond']['capacity_m3'] <= stats['estimated_volume_m3']
            assert len(data['catchment']['boundary']) >= 3
            assert data['water_screening']['status'] == 'applied'
            print(json.dumps({'upload': index, 'seconds': round(time.monotonic()-start, 2), 'status': data['analysis_status'], 'catchment_m2': stats['catchment_area_sqm'], 'runoff_m3': stats['estimated_volume_m3'], 'candidates': len(data['candidate_options'])}), flush=True)
            return data
        async def probes():
            latencies = []
            for _ in range(15):
                start = time.monotonic()
                response = await client.get('/health/ready')
                assert response.status_code == 200
                latencies.append(time.monotonic()-start)
                await asyncio.sleep(1)
            print(json.dumps({'health_probes': len(latencies), 'max_seconds': round(max(latencies), 3)}), flush=True)
        if args.selections_only:
            data = await upload(1)
            candidate = data['candidate_options'][-1]
            forms = [
                {'selection_mode': 'point', 'selected_lat': str(candidate['lat']), 'selected_lng': str(candidate['lng'])},
                {'selection_mode': 'region', 'selected_region': json.dumps(data['study_area_boundary'])},
            ]
            for form in forms:
                response = await client.post('/api/analyze-contour', files={'contour_map': ('contours_1m.kml', content)}, data=form)
                response.raise_for_status()
                result = response.json()
                assert result['analysis_status'] == 'complete', result.get('quality')
                assert result['selection']['mode'] == form['selection_mode']
                if form['selection_mode'] == 'point':
                    assert abs(result['pond_location']['lat'] - candidate['lat']) < .001
                    assert abs(result['pond_location']['lng'] - candidate['lng']) < .001
                print(json.dumps({'selection': form['selection_mode'], 'status': result['analysis_status'], 'catchment_m2': result['catchment']['area_sqm']}), flush=True)
        else:
            await asyncio.gather(upload(1), upload(2), probes())
        for path in ['/', '/docs', '/openapi.json']:
            assert (await client.get(path)).status_code == 200
        assert (await client.post('/api/analyze-contour')).status_code == 422
        print('SUBMISSION_CHECKS_PASSED', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
