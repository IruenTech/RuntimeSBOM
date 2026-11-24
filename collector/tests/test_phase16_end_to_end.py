"""Two actual JVM processes: persistent queue survives collector outage and JVM restart.
The build used by this test intentionally has a NON-INSTRUMENTING ASM stub.
This tests delivery resilience, NOT bytecode instrumentation.
"""
import json
import os
import socket
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
TOKEN = 'phase16-end-to-end-secret-123456789'


class CrossJvmRestartTests(unittest.TestCase):
    def test_queue_survives_process_restart_then_delivers(self):
        jar = ROOT/'target/offline-validation/agent-validation-only.jar'
        demo = ROOT/'target/offline-validation/demo.jar'
        if not (jar.is_file() and demo.is_file()):
            self.skipTest('Compile the offline transport Agent before running this test')
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0))
                port = sock.getsockname()[1]
            endpoint = f'http://127.0.0.1:{port}/api/v1/sbom'
            queue = base / 'queue'
            def run_agent(asset, destination):
                options = f'output={base/destination},interval=0,resourceProbe=false,assetId={asset},queueDir={queue},queueDrainInterval=15,httpTimeoutMs=500,collectorUrl={endpoint}'
                return subprocess.run(['java',f'-javaagent:{jar}={options}','-cp',str(demo),'example.Demo'],
                    env={**os.environ,'RUNTIMESBOM_TOKEN':TOKEN},capture_output=True,text=True,timeout=25)
            first = run_agent('asset-before-restart','first.json')
            self.assertEqual(first.returncode,0,first.stderr)
            self.assertEqual(len(list(queue.glob('*.json'))),1,first.stderr)
            first_json = json.loads((base/'first.json').read_text())
            self.assertEqual(first_json['bomFormat'],'CycloneDX')
            collector = Server(('127.0.0.1', port),Handler,base/'collector',{TOKEN:'local'})
            worker = threading.Thread(target=collector.serve_forever,daemon=True)
            worker.start()
            try:
                second = run_agent('asset-after-restart','second.json')
                self.assertEqual(second.returncode,0,second.stderr)
                self.assertEqual(list(queue.glob('*.json')),[],second.stderr)
                req = Request(f'http://127.0.0.1:{port}/api/v1/assets',
                              headers={'Authorization':'Bearer '+TOKEN})
                with urlopen(req, timeout=5) as res:
                    assets = json.load(res)['assets']
                self.assertEqual([(a['asset'],a['snapshotCount']) for a in assets],
                    [('asset-after-restart',1),('asset-before-restart',1)])
                self.assertEqual(collector.conn.execute('SELECT COUNT(DISTINCT delivery_id) FROM snapshots').fetchone()[0],2)
            finally:
                collector.shutdown()
                worker.join(timeout=5)
                collector.server_close()
