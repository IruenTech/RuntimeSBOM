"""Phase21 gate must never approve a staging review from fixtures/fake evidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('gate21', ROOT/'scripts/phase21-release-gate.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.agent=self.root/'nonexistent.jar'
        self.jdk=self.root/'jdk'; self.jdk.mkdir()
        self.live=self.root/'live'; self.live.mkdir()
        self.fixture=self.root/'fixture.json'
        self.fixture.write_text(json.dumps({'status':'PASS','realTomcatSpringBootTest':False,
           'samePurlDifferentJarSha256':True,
           'results':{'loaded-only':{'truePositives':3,'falsePositives':0,'falseNegatives':0},
                      'asm-traced':{'truePositives':3,'falsePositives':0,'falseNegatives':0}}}))

    def gate(self):
        return module.evaluate(self.agent,self.jdk,self.live,self.fixture)

    def test_missing_official_is_hold(self):
        report=self.gate()
        self.assertEqual(report['stagingReview'],'HOLD')
        self.assertEqual(report['productionDeployment'],'HOLD')
        self.assertEqual(report['successfulChecks'],1)

    def test_fixture_does_not_unlock_official(self):
        report=self.gate()
        self.assertEqual(report['checks']['localHttpProvenanceFixture'],'PASS')
        self.assertEqual(report['checks']['officialShadedJarAudit'],'MISSING_OR_INVALID')
        self.assertEqual(report['checks']['spring-boot2'],'MISSING_OR_INVALID')

    def test_unsupported_evidence_mode_does_not_pass(self):
        path=self.live/'spring-boot2';path.mkdir()
        (path/'phase21-summary.json').write_text(json.dumps({
            'status':'PASS','evidenceMode':'JDK_INTERNAL_TEST_ONLY',
            'officialJarSha256':'missing','archiveEvidenceMatches':True,
            'humanProductionApproval':'REQUIRED','embeddedDependencySha256':'0'*64}))
        self.assertEqual(self.gate()['checks']['spring-boot2'],'MISSING_OR_INVALID')

    def test_modified_fixture_does_not_pass(self):
        doc=json.loads(self.fixture.read_text())
        doc['results']['asm-traced']['falsePositives']=1
        self.fixture.write_text(json.dumps(doc))
        self.assertEqual(self.gate()['checks']['localHttpProvenanceFixture'],'MISSING_OR_INVALID')

if __name__=='__main__':unittest.main()
