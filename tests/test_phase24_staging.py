"""Phase 24 negative tests: absent/altered binary proof and SBOM observability.
Tests deliberately patch audit for pure decision-logic verification. No synthetic
PASS is exported as a real official binary acceptance report.
"""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod

preflight=load('phase24_preflight_test','phase24-check-binary.py')
manifest=load('phase24_manifest_test','phase24-staging-manifest.py')

class Phase24Preflight(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.agent=self.root/'agent.jar';self.agent.write_bytes(b'not-official-jar-fixture')
        self.sha=hashlib.sha256(self.agent.read_bytes()).hexdigest()
        self.proof=self.root/'build.json'
        self.proof.write_text(json.dumps({'status':'PASS','version':'1.0.0-rc16',
            'artifactSha256':self.sha,'mavenPackageSucceeded':True,
            'asmDependency':'org.ow2.asm:asm:jar:9.7.1'}))
    def tearDown(self):self.tmp.cleanup()
    def fake_audit(self):return type('A',(),{'audit':lambda _self,x:{'status':'PASS','sha256':hashlib.sha256(Path(x).read_bytes()).hexdigest()}})()
    def test_valid_proof_logic_still_production_hold(self):
        with patch.object(preflight,'load',return_value=self.fake_audit()):r=preflight.inspect(self.agent,self.proof)
        self.assertEqual(r['status'],'PASS')
        self.assertEqual(r['productionDeployment'],'HOLD')
    def test_tampered_jar_rejected(self):
        self.agent.write_bytes(b'tampered')
        with patch.object(preflight,'load',return_value=self.fake_audit()):r=preflight.inspect(self.agent,self.proof)
        self.assertEqual(r['status'],'HOLD')
        self.assertFalse(r['checks']['exactArtifactSha256'])
    def test_wrong_version_rejected(self):
        obj=json.loads(self.proof.read_text());obj['version']='1.0.0-rc14';self.proof.write_text(json.dumps(obj))
        with patch.object(preflight,'load',return_value=self.fake_audit()):r=preflight.inspect(self.agent,self.proof)
        self.assertEqual(r['status'],'HOLD')
    def test_wrong_asm_rejected(self):
        obj=json.loads(self.proof.read_text());obj['asmDependency']='org.ow2.asm:asm:jar:9.6';self.proof.write_text(json.dumps(obj))
        with patch.object(preflight,'load',return_value=self.fake_audit()):r=preflight.inspect(self.agent,self.proof)
        self.assertEqual(r['status'],'HOLD')
    def test_missing_proof_rejected(self):
        self.proof.unlink()
        with patch.object(preflight,'load',return_value=self.fake_audit()):r=preflight.inspect(self.agent,self.proof)
        self.assertEqual(r['status'],'HOLD')
    def test_missing_agent_rejected(self):
        self.agent.unlink()
        with patch.object(preflight,'load',return_value=type('A',(),{'audit':lambda _self,x:{'status':'FAIL','sha256':None}})()):
            r=preflight.inspect(self.agent,self.proof)
        self.assertEqual(r['status'],'HOLD')

class Phase24Manifest(unittest.TestCase):
    def test_required_input_evidence_count(self):
        with tempfile.TemporaryDirectory() as t:
            required=manifest.files_required(Path(t))
            self.assertEqual(len(required),3+4*2+4*8)
            self.assertIn(Path(t)/'results/phase22/live/tomcat10/asm-traced/sbom.json',required)
    def test_missing_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as t:
            r=manifest.evaluate(t)
            self.assertEqual(r['stagingReview'],'HOLD')
            self.assertEqual(r['productionDeployment'],'HOLD')
            self.assertFalse(r['checks']['baseExactBinaryReview'])
    def test_invalid_sbom_file_fails(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bom.json';p.write_text('{invalid')
            self.assertFalse(all(manifest.sbom_runtime_checks(p).values()))
    def test_missing_agent_tool_version_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bom.json';p.write_text(json.dumps({'bomFormat':'CycloneDX','specVersion':'1.6','metadata':{
                'tools':{'components':[{'name':'RuntimeSBOM-Agent','version':'rc14'}]},'properties':[]},'components':[]}))
            self.assertFalse(manifest.sbom_runtime_checks(p).get('exactAgentVersion'))
    def test_digest_detects_file_modification(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'some.json';p.write_text('{}');first=manifest.digest(p)
            p.write_text('{"tampered":true}')
            self.assertNotEqual(first,manifest.digest(p))

if __name__=='__main__':unittest.main()
