"""Negative and fixture-positive tests for fail-closed release evidence validation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('phase22_evidence',ROOT/'scripts/phase22-evidence-gate.py')
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
SHA='a'*64


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data),encoding='utf-8')


class Phase22AcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.jar=self.root/'agent.jar';self.jar.write_bytes(b'mocked binary for evidence-gate unit test only')
        self.build=self.root/'build.json'
        self.jdks=self.root/'jdks';self.live=self.root/'live'
        self.mock_audit=patch.object(gate,'load_audit',return_value=type('Auditor',(),{
            'audit':staticmethod(lambda _: {'status':'PASS','sha256':SHA})}))
        self.mock_audit.start();self.addCleanup(self.mock_audit.stop)
        save(self.build,{'status':'PASS','mavenPackageSucceeded':True,
            'artifactSha256':SHA,'asmDependency':'org.ow2.asm:asm:jar:9.7.1'})
        for major in gate.JDKS:
            save(self.jdks/f'jdk-{major}.json',{'status':'PASS','evidenceMode':'OFFICIAL_SHADED_RUNTIME',
                'jdkMajor':major,'officialJarSha256':SHA,'methodEvidence':True,'artifactAudit':'PASS'})
        for app in gate.APPS:
            save(self.live/app/'phase21-summary.json',self.app_report(app))

    def app_report(self,app):
        mode=lambda executed,tps:{'evidence':{'purlFound':True,'methodExecuted':executed},'http':{'successTps':tps}}
        return {'application':app,'status':'PASS','evidenceMode':'OFFICIAL_SHADED_RUNTIME',
            'officialJarSha256':SHA,'archiveEvidenceMatches':True,'applicationArchiveSha256':'b'*64,
            'embeddedDependencySha256':'c'*64,'httpModes':{
                'baseline':mode(False,100),'loaded-only':mode(False,98),'asm-traced':mode(True,92)},
            'comparison':{'tpsDeltaPercent':-8.,'p95DeltaPercent':10.}}

    def result(self):return gate.validate(self.jar,self.jdks,self.live,self.build)

    def test_consistent_fixture_allows_only_human_review(self):
        r=self.result();self.assertEqual(r['stagingReview'],'ELIGIBLE_FOR_HUMAN_REVIEW')
        self.assertEqual(r['productionDeployment'],'HOLD')
        self.assertEqual(len(r['checks']),10)

    def test_missing_jdk_is_hold(self):
        (self.jdks/'jdk-8.json').unlink()
        self.assertEqual(self.result()['stagingReview'],'HOLD')

    def test_test_only_agent_evidence_is_rejected(self):
        path=self.jdks/'jdk-21.json';report=json.loads(path.read_text());report['evidenceMode']='JDK_INTERNAL_ASM_TEST_ONLY';save(path,report)
        self.assertFalse(self.result()['checks']['jdk21'])

    def test_wrong_agent_sha_is_rejected(self):
        path=self.live/'spring-boot2/phase21-summary.json';report=json.loads(path.read_text());report['officialJarSha256']='d'*64;save(path,report)
        self.assertFalse(self.result()['checks']['spring-boot2'])

    def test_false_execution_claim_on_loading_only_is_rejected(self):
        path=self.live/'spring-boot3/phase21-summary.json';report=json.loads(path.read_text());report['httpModes']['loaded-only']['evidence']['methodExecuted']=True;save(path,report)
        self.assertFalse(self.result()['checks']['spring-boot3'])

    def test_p95_regression_rejected(self):
        path=self.live/'tomcat9/phase21-summary.json';report=json.loads(path.read_text());report['comparison']['p95DeltaPercent']=26.;save(path,report)
        self.assertFalse(self.result()['checks']['tomcat9'])

    def test_nan_performance_rejected(self):
        path=self.live/'tomcat10/phase21-summary.json';report=json.loads(path.read_text());report['comparison']['tpsDeltaPercent']=float('nan');save(path,report)
        self.assertFalse(self.result()['checks']['tomcat10'])

    def test_wrong_asm_dependency_is_rejected(self):
        report=json.loads(self.build.read_text());report['asmDependency']='org.ow2.asm:asm:jar:9.6';save(self.build,report)
        self.assertFalse(self.result()['checks']['mavenBuildEvidence'])

    def test_missing_build_proof_is_rejected(self):
        self.build.unlink()
        self.assertFalse(self.result()['checks']['mavenBuildEvidence'])

    def test_archive_mismatch_rejected(self):
        path=self.live/'tomcat10/phase21-summary.json';report=json.loads(path.read_text());report['archiveEvidenceMatches']=False;save(path,report)
        self.assertFalse(self.result()['checks']['tomcat10'])

    def test_no_official_jar_still_hold_with_real_audit(self):
        self.mock_audit.stop()
        self.addCleanup(lambda:None)
        self.assertEqual(self.result()['stagingReview'],'HOLD')
        # restore for any later test (setUp fixture isolation)
        self.mock_audit.start()

if __name__=='__main__':unittest.main()
