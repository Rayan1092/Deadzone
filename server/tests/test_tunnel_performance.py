import asyncio
import json

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.testclient import TestClient

from deadzone.network.lite import LiteScreen
from deadzone.web_assets import ProductionFiles


def test_production_hash_cache_gzip_and_revalidated_html(tmp_path):
    assets = tmp_path / 'assets'
    assets.mkdir()
    (assets / 'bundle-Ab12_xY9.js').write_text('const example = 1;\n' * 500)
    (assets / 'stable.js').write_text('stable')
    (tmp_path / 'index.html').write_text('<html>Production build</html>')
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.mount('/', ProductionFiles(directory=tmp_path, html=True))
    with TestClient(app) as client:
        response = client.get('/assets/bundle-Ab12_xY9.js')
        assert response.headers['content-encoding'] == 'gzip'
        assert response.headers['cache-control'] == 'public, max-age=31536000, immutable'
        assert 'Accept-Encoding' in response.headers['vary']
        unchanged = client.get('/assets/bundle-Ab12_xY9.js', headers={'If-None-Match': response.headers['etag']})
        assert unchanged.status_code == 304
        assert 'immutable' in unchanged.headers['cache-control']
        assert client.get('/').headers['cache-control'] == 'no-cache'
        assert 'immutable' not in client.get('/assets/stable.js').headers.get('cache-control', '')
        assert 'immutable' not in client.get('/assets/missing-Ab12_xY9.js').headers.get('cache-control', '')


def test_lite_initial_snapshot_and_alternate_ticks_preserve_other_reports():
    profile = LiteScreen()
    tick = json.dumps({'t': 'tick', 'data': {'reality': {'robots': [
        {'id': 'R1', 'lidar': [[1, 2]], 'camera': [{'id': 'S1'}], 'battery_pct': 99}]}, 'command': {'stale_s': 3}}})
    initial = json.loads(profile.transform(tick, initial=True))
    assert initial['data']['reality']['robots'][0]['lidar'] == []
    assert profile.transform(tick) is None
    result = json.loads(profile.transform(tick))
    assert result['data']['reality']['robots'][0]['camera'] == [{'id': 'S1'}]
    assert result['data']['command'] == {'stale_s': 3}
    assert len([value for _ in range(20) if (value := profile.transform(tick)) is not None]) == 10
    for kind in ('maps', 'map_patch', 'event', 'report', 'error', 'control'):
        message = json.dumps({'t': kind, 'data': {'value': 1}})
        assert profile.transform(message) == message


def test_lite_and_full_sockets_do_not_share_reduced_payloads(monkeypatch):
    from deadzone.app import Hub
    class Socket:
        def __init__(self): self.messages = []
        async def send_text(self, message): self.messages.append(json.loads(message))
    full, lite = Socket(), Socket()
    hub = Hub.__new__(Hub)
    hub.screens = {full, lite}
    hub.lite_screens = {lite: LiteScreen()}
    hub.compact_clients = {full, lite}
    hub.delta_screens = {}
    tick = json.dumps({'t': 'tick', 'data': {'reality': {'robots': [{'id': 'R1', 'lidar': [[1, 2]]}]}}})
    async def send():
        for _ in range(10): await hub.send_all(hub.screens, tick)
    asyncio.run(send())
    assert len(full.messages) == 10 and len(lite.messages) == 5
    assert all(m['data']['reality']['robots'][0]['lidar'] == [[1, 2]] for m in full.messages)
    assert all(m['data']['reality']['robots'][0]['lidar'] == [] for m in lite.messages)


def test_compact_default_and_explicit_legacy_opt_out(monkeypatch):
    from deadzone.app import Hub
    monkeypatch.setenv('DETECTOR', 'sim')
    monkeypatch.delenv('DZ_COMPACT_STREAM', raising=False)
    assert Hub().compact_stream
    monkeypatch.setenv('DZ_COMPACT_STREAM', '0')
    assert not Hub().compact_stream


def test_real_app_production_root_and_lite_handshake(monkeypatch):
    from deadzone import app as api
    monkeypatch.setenv('DETECTOR', 'sim')
    monkeypatch.setenv('DZ_AUTOSTART', '0')
    monkeypatch.setenv('DZ_CONTROL_LEASES', '0')
    monkeypatch.setenv('DZ_VOICE', '0')
    monkeypatch.delenv('DZ_COMPACT_STREAM', raising=False)
    monkeypatch.setattr(api, 'hub', api.Hub())
    with TestClient(api.app) as client:
        root = client.get('/')
        assert root.status_code == 200
        assert '/assets/index-' in root.text and '/@vite/client' not in root.text
        assert root.headers['cache-control'] == 'no-cache'
        assert client.get('/phone').headers['cache-control'] == 'no-cache'
        for query in ('lite', 'lite=1'):
            with client.websocket_connect('/ws/screen?map_deltas=1&' + query) as ws:
                hello, maps, tick = ws.receive_json(), ws.receive_json(), ws.receive_json()
                assert hello['data']['screen_profile']['tick_stride'] == 2
                assert 'compact_stream' in hello['data']
                assert maps['data']['encoding'] == 'zlib-base64'
                assert all(r['lidar'] == [] for r in tick['data']['reality']['robots'])
        with client.websocket_connect('/ws/screen?lite=0') as ws:
            assert 'screen_profile' not in ws.receive_json()['data']
    assert not api.hub.lite_screens
