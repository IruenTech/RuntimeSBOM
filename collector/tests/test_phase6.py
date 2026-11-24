import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Handler,Server,evidence

TOK='unit-test-secret-token-12345'
ALT='other-tenant-secret-token-54321'

def component(name, state='CLASS_LOADED', calls=0):
    return {'type':'library','name':name,'version':'1.0','purl':'pkg:maven/example/'+name+'@1.0',
            'properties':[{'name':'runtimeSbom:runtimeEvidenceState','value':state},
                          {'name':'runtimeSbom:observedMethodEntryCount','value':str(calls)}]}

def bom(*components):
    return {'bomFormat':'CycloneDX','specVersion':'1.6','components':list(components)}

class Phase6Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=Server(('127.0.0.1',0),Handler,self.tmp.name,{TOK:'tenant-a',ALT:'tenant-b'})
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.thread.join();self.server.server_close();self.tmp.cleanup()
    def call(self,method,path,payload=None,token=TOK,asset='was01'):
        headers={'Authorization':'Bearer '+token,'X-RuntimeSBOM-Asset':asset}
        raw=json.dumps(payload).encode() if payload is not None else None
        req=Request(self.base+path,data=raw,headers=headers,method=method)
        try:
            with urlopen(req,timeout=5) as resp:
                return resp.status,json.load(resp)
        except HTTPError as e:
            return e.code,json.load(e)
    def test_inventory_evidence_prioritization(self):
        self.call('POST','/api/v1/sbom',bom(component('alpha','METHOD_EXECUTED',5),component('beta')))
        findings={'source':'OSV','results':[{'purl':'pkg:maven/example/alpha@1.0','vulns':[{'id':'GHSA-test-1'}]},
                  {'purl':'pkg:maven/example/beta@1.0','vulns':[{'id':'CVE-test-1'}]}]}
        self.assertEqual(self.call('POST','/api/v1/findings/import',findings)[0],200)
        status,dashboard=self.call('GET','/api/v1/dashboard')
        self.assertEqual(status,200)
        self.assertEqual(dashboard['componentCount'],2)
        self.assertEqual(dashboard['findingOccurrences'],2)
        _,items=self.call('GET','/api/v1/components')
        items={c['name']:c for c in items['components']}
        self.assertEqual(items['alpha']['triage'],'review-executed')
        self.assertEqual(items['alpha']['methodCalls'],5)
        self.assertEqual(items['beta']['triage'],'review-loaded')
        self.assertEqual(items['beta']['methodCalls'],0)
    def test_changes_and_tenant_isolation(self):
        self.call('POST','/api/v1/sbom',bom(component('alpha')))
        self.call('POST','/api/v1/sbom',bom(component('alpha'),component('beta')))
        _,alerts=self.call('GET','/api/v1/alerts')
        self.assertEqual(len(alerts['alerts']),1)
        self.assertEqual(alerts['alerts'][0]['added'],['purl:pkg:maven/example/beta@1.0'])
        _,other=self.call('GET','/api/v1/dashboard',token=ALT)
        self.assertEqual(other['componentCount'],0)
        _,empty=self.call('GET','/api/v1/alerts',token=ALT)
        self.assertEqual(empty['alerts'],[])
    def test_findings_replace_and_auth(self):
        url='pkg:maven/example/alpha@1.0'
        payload={'results':[{'purl':url,'vulns':[{'id':'CVE-2020-1234'}]}]}
        self.assertEqual(self.call('POST','/api/v1/findings/import',payload,token='bad')[0],401)
        self.assertEqual(self.call('POST','/api/v1/findings/import',payload)[0],200)
        self.call('POST','/api/v1/sbom',bom(component('alpha')))
        self.assertEqual(self.call('GET','/api/v1/dashboard')[1]['findingOccurrences'],1)
        self.assertEqual(self.call('POST','/api/v1/findings/import',{'results':[{'purl':url,'vulns':[]} ]})[0],200)
        self.assertEqual(self.call('GET','/api/v1/dashboard')[1]['findingOccurrences'],0)
    def test_html_static_and_no_token_in_url(self):
        for route,ctype in [('/dashboard','text/html'),('/dashboard.js','text/javascript'),('/dashboard.css','text/css')]:
            with urlopen(self.base+route,timeout=5) as r:
                self.assertEqual(r.status,200)
                self.assertIn(ctype,r.headers.get('Content-Type'))
                self.assertIn('Content-Security-Policy',r.headers)
    def test_bad_findings_rejected(self):
        self.assertEqual(self.call('POST','/api/v1/findings/import',{'results':[{'purl':'invalid','vulns':[]} ]})[0],422)
        self.assertEqual(self.call('POST','/api/v1/findings/import',{'results':'not-list'})[0],422)

if __name__=='__main__':unittest.main()
