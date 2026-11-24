import copy
import importlib.util
import json
from pathlib import Path
import unittest
import tempfile
import subprocess

ROOT=Path(__file__).resolve().parent.parent
SPEC=importlib.util.spec_from_file_location('phase17_loader',str(ROOT/'scripts/phase17-verify-loader.py'))
MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)
GATE=importlib.util.spec_from_file_location('phase17_gate',str(ROOT/'scripts/phase17-release-gate.py'))
GATE_MODULE=importlib.util.module_from_spec(GATE);GATE.loader.exec_module(GATE_MODULE)

class Phase17ValidationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=ROOT/'target/phase17-loader/fixture-core-1.2.3.jar'
        self.bom=json.loads((ROOT/'target/phase17-loader/loader-sbom.json').read_text())
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def validate(self, body):
        p=Path(self.temp.name)/'sbom.json'
        p.write_text(json.dumps(body))
        return MODULE.verify(p,self.fixture)

    def test_real_fixture_succeeds(self):
        self.assertEqual(self.validate(self.bom)['methodCounts'],[0,3,5])

    def test_missing_loader_rejected(self):
        copybom=copy.deepcopy(self.bom)
        comp=[c for c in copybom['components'] if c.get('purl')=='pkg:maven/com.example.fixture/fixture-core@1.2.3']
        copybom['components'].remove(comp[0])
        with self.assertRaises(AssertionError):self.validate(copybom)

    def test_fake_execution_rejected(self):
        copybom=copy.deepcopy(self.bom)
        comp=[c for c in copybom['components'] if c.get('purl')=='pkg:maven/com.example.fixture/fixture-core@1.2.3']
        for p in comp[0]['properties']:
            if p['name']=='runtimeSbom:observedMethodEntryCount':p['value']='999'
        with self.assertRaises(AssertionError):self.validate(copybom)

    def test_wrong_hash_rejected(self):
        copybom=copy.deepcopy(self.bom)
        comp=[c for c in copybom['components'] if c.get('purl')=='pkg:maven/com.example.fixture/fixture-core@1.2.3']
        comp[0]['hashes'][0]['content']='0'*64
        with self.assertRaises(AssertionError):self.validate(copybom)

    def test_field_tool_rejects_test_only_internal_asm_agent(self):
        evidence=Path(self.temp.name)/'output.json'
        cmd=['python3','scripts/phase17-field-evidence.py','--was','JEUS',
             '--asset','staging-1','--sbom',str(ROOT/'target/phase17-loader/loader-sbom.json'),
             '--agent',str(ROOT/'target/jdk-asm-verification/agent-test-only.jar'),
             '--expected-purl','pkg:maven/com.example.fixture/fixture-core@1.2.3',
             '--out',str(evidence)]
        p=subprocess.run(cmd,cwd=str(ROOT),capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('not the official relocated-ASM build',p.stderr)
        self.assertFalse(evidence.exists())

    def test_missing_official_never_approves(self):
        decisions=GATE_MODULE.decide([{'status':'PASS'}], 'NOT_RUN', {'JEUS':'NOT_RUN'}, 'NOT_RUN')
        self.assertEqual(decisions['productionDeployment'],'HOLD')
        self.assertEqual(decisions['stagingReview'],'HOLD')

    def test_official_approval_still_production_hold(self):
        decisions=GATE_MODULE.decide([{'status':'PASS'}], 'PASS', {'JEUS':'NOT_RUN'}, 'NOT_RUN')
        self.assertEqual(decisions['productionDeployment'],'HOLD')

if __name__=='__main__':unittest.main()
