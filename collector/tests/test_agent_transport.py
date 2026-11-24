"""Offline Java 8 agent-to-collector transport smoke test.
Compiles with a dummy transformer solely to validate non-ASM upload plumbing.
Do NOT distribute the dummy agent as a fully instrumenting build.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Server, Handler

ROOT = Path(__file__).resolve().parents[2]

class AgentTransportTest(unittest.TestCase):
    def test_java_upload(self):
        jar = ROOT / 'target/offline-validation/agent-validation-only.jar'
        demo = ROOT / 'target/offline-validation/demo.jar'
        if not jar.exists() or not demo.exists():
            self.skipTest('run scripts/validate-offline.sh first')
        with tempfile.TemporaryDirectory() as path:
            token = 'test-secret-123456789-abcdef'
            server = Server(('127.0.0.1',0), Handler, path, {token:'local'})
            t = threading.Thread(target=server.serve_forever,daemon=True)
            t.start()
            try:
                sbom = Path(path) / 'runtime-sbom.json'
                agent_arg = f'-javaagent:{jar}=output={sbom},interval=0,assetId=legacy-was-01,collectorUrl=http://127.0.0.1:{server.server_port}/api/v1/sbom'
                result = subprocess.run(['java',agent_arg,'-cp',str(demo),'example.Demo'],env={**os.environ,'RUNTIMESBOM_TOKEN':token},capture_output=True,text=True,timeout=25)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertTrue(sbom.exists(),result.stderr)
                self.assertEqual(json.loads(sbom.read_text())['specVersion'],'1.6')
                req=Request(f'http://127.0.0.1:{server.server_port}/api/v1/snapshots?asset=legacy-was-01',headers={'Authorization':'Bearer '+token})
                with urlopen(req,timeout=3) as response:
                    data=json.load(response)
                self.assertEqual(len(data['snapshots']),1)
                self.assertEqual(data['snapshots'][0]['components'], len(json.loads(sbom.read_text())['components']))
            finally:
                server.shutdown();t.join();server.server_close()
