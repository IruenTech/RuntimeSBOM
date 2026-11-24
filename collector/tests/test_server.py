import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Server, Handler, compare

TOKEN = 'a-super-secret-token-for-testing'

def bom(*names):
    return {'bomFormat': 'CycloneDX', 'specVersion': '1.6',
            'components': [{'type': 'library', 'name': n, 'version': '1.0', 'purl': f'pkg:maven/test/{n}@1.0'} for n in names]}

class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = Server(('127.0.0.1', 0), Handler, self.temp.name, {TOKEN:'tenantA', 'another-secret-token-9876':'tenantB'})
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:%d' % self.server.server_port

    def tearDown(self):
        self.server.shutdown(); self.thread.join(); self.server.server_close(); self.temp.cleanup()

    def call(self, method, path, data=None, token=TOKEN, asset='was-01'):
        headers = {'Authorization': 'Bearer ' + token, 'X-RuntimeSBOM-Asset': asset}
        request = Request(self.base + path, headers=headers, data=json.dumps(data).encode() if data is not None else None, method=method)
        try:
            with urlopen(request, timeout=3) as r:
                return r.status, json.load(r)
        except HTTPError as e:
            return e.code, json.load(e)

    def test_history_and_diff(self):
        status, a = self.call('POST','/api/v1/sbom', bom('alpha','beta'))
        self.assertEqual(status,201)
        status, b = self.call('POST','/api/v1/sbom', bom('beta','gamma'))
        self.assertEqual(status,201)
        status, assets = self.call('GET','/api/v1/assets')
        self.assertEqual(status,200)
        self.assertEqual(assets['assets'][0]['asset'],'was-01')
        status, history = self.call('GET','/api/v1/snapshots?asset=was-01')
        self.assertEqual(status,200)
        self.assertEqual(len(history['snapshots']),2)
        status, diff = self.call('GET',f"/api/v1/diff?asset=was-01&from={a['snapshotId']}&to={b['snapshotId']}")
        self.assertEqual(status,200)
        self.assertEqual(diff['added'], ['purl:pkg:maven/test/gamma@1.0'])
        self.assertEqual(diff['removed'], ['purl:pkg:maven/test/alpha@1.0'])
        self.assertEqual(diff['unchangedCount'], 1)

    def test_auth_and_tenant_asset_isolation(self):
        status, original = self.call('POST','/api/v1/sbom',bom('private'))
        self.assertEqual(status,201)
        status, listing = self.call('GET','/api/v1/snapshots?asset=was-01',token='another-secret-token-9876')
        self.assertEqual(status,200)
        self.assertEqual(listing['snapshots'],[])
        status, _ = self.call('GET',f"/api/v1/diff?asset=was-01&from={original['snapshotId']}&to={original['snapshotId']}",token='another-secret-token-9876')
        self.assertEqual(status,404)
        status, _ = self.call('GET','/api/v1/snapshots?asset=was-01',token='invalid')
        self.assertEqual(status,401)
        status, _ = self.call('GET','/api/v1/snapshots?asset=other')
        self.assertEqual(status,200)

    def test_reject_bad_envelope_and_asset(self):
        self.assertEqual(self.call('POST','/api/v1/sbom',{'bomFormat':'wrong','components':[]})[0], 422)
        self.assertEqual(self.call('POST','/api/v1/sbom',bom('a'),asset='../oops')[0],400)

    def test_persists_after_restart(self):
        self.call('POST','/api/v1/sbom',bom('alpha'))
        self.server.shutdown(); self.thread.join(); self.server.server_close()
        self.server = Server(('127.0.0.1',0),Handler,self.temp.name,{TOKEN:'tenantA'})
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:%d' % self.server.server_port
        self.assertEqual(len(self.call('GET','/api/v1/snapshots?asset=was-01')[1]['snapshots']),1)

if __name__ == '__main__':
    unittest.main()
