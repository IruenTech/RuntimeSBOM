#!/usr/bin/env python3
"""Seed the local collector with synthetic demo data (no live vulnerability assertions)."""
import json
import os
from urllib.request import Request,urlopen

BASE='http://127.0.0.1:8765'
TOKEN=os.environ.get('RUNTIMESBOM_TOKEN','')
if not TOKEN: raise SystemExit('Set RUNTIMESBOM_TOKEN')

def post(path,doc,asset='was-demo-01'):
    req=Request(BASE+path,method='POST',data=json.dumps(doc).encode(),headers={'Authorization':'Bearer '+TOKEN,'X-RuntimeSBOM-Asset':asset,'Content-Type':'application/json'})
    with urlopen(req,timeout=10) as res: print(res.status,res.read().decode())

def lib(name,state,calls):
    return {'type':'library','name':name,'version':'1.0.0','purl':'pkg:maven/demo/'+name+'@1.0.0',
      'properties':[{'name':'runtimeSbom:runtimeEvidenceState','value':state}, {'name':'runtimeSbom:observedMethodEntryCount','value':str(calls)}]}

def bom(*items): return {'bomFormat':'CycloneDX','specVersion':'1.6','version':1,'components':list(items)}

post('/api/v1/sbom',bom(lib('sample-core','METHOD_EXECUTED',24),lib('sample-logging','CLASS_LOADED',0)))
post('/api/v1/sbom',bom(lib('sample-core','METHOD_EXECUTED',48),lib('sample-web','CLASS_LOADED',0)))
post('/api/v1/sbom',bom(lib('sample-core','CLASS_LOADED',0)),asset='was-demo-02')
post('/api/v1/findings/import',{'source':'synthetic-demo','results':[{'purl':'pkg:maven/demo/sample-core@1.0.0','vulns':[{'id':'DEMO-ONLY-001','summary':'Synthetic example, not a real vulnerability','severity':'unknown'}]}]})
