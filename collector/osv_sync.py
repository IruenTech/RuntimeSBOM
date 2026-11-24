#!/usr/bin/env python3
"""Opt-in OSV querybatch sync. Requires outbound HTTPS; never runs automatically.
Only versioned PURLs from latest tenant-owned SBOMs are queried.
"""
import argparse
import json
import os
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

OSV_URL = 'https://api.osv.dev/v1/querybatch'

def request_json(url, token=None, payload=None):
    headers = {'Accept':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    if payload is not None: headers['Content-Type']='application/json'
    req=Request(url,data=json.dumps(payload).encode('utf-8') if payload is not None else None,headers=headers,method='POST' if payload is not None else 'GET')
    with urlopen(req,timeout=25) as res:
        return json.load(res)

def sync(base,token,batch_size=100):
    if urlsplit(base).scheme not in ('http','https'): raise ValueError('Invalid collector URL')
    if urlsplit(base).scheme!='https' and not base.startswith('http://127.0.0.1:') and not base.startswith('http://localhost:'):
        raise ValueError('Use HTTPS for remote collector')
    components=request_json(base.rstrip('/')+'/api/v1/components',token)['components']
    purls=sorted({c['purl'] for c in components if isinstance(c.get('purl'),str) and c['purl'].startswith('pkg:') and '@' in c['purl']})
    total=0
    for i in range(0,len(purls),batch_size):
        batch=purls[i:i+batch_size]
        osv=request_json(OSV_URL,payload={'queries':[{'package':{'purl':p}} for p in batch]})
        results=osv.get('results',[])
        if len(results)!=len(batch): raise RuntimeError('Unexpected OSV querybatch result size')
        normalized=[]
        for p, result in zip(batch,results):
            # Querybatch returns vulnerability IDs; no severity is inferred.
            normalized.append({'purl':p,'vulns':[{'id':v['id'],'summary':'','severity':'unknown'} for v in result.get('vulns',[]) if isinstance(v,dict) and isinstance(v.get('id'),str)]})
        request_json(base.rstrip('/')+'/api/v1/findings/import',token,{'source':'OSV','results':normalized})
        total+=len(batch)
    return {'queriedPurls':total}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--collector',default='http://127.0.0.1:8765')
    a=parser.parse_args()
    token=os.environ.get('RUNTIMESBOM_TOKEN','')
    if not token: parser.error('RUNTIMESBOM_TOKEN environment variable required')
    try: print(json.dumps(sync(a.collector,token)))
    except Exception as error: print('OSV sync failed: '+str(error),file=sys.stderr);sys.exit(1)
