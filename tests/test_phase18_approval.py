"""Fail-closed release evidence tests. Fake JAR bytes only prove gate logic, not ASM provenance."""
import importlib.machinery
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parent.parent
AUDIT=importlib.machinery.SourceFileLoader('p18_audit',str(ROOT/'scripts/phase18-audit-jar.py')).load_module()
GATE=importlib.machinery.SourceFileLoader('p18_gate',str(ROOT/'scripts/phase18-acceptance.py')).load_module()

HEADER=b'\xca\xfe\xba\xbe\x00\x00\x00\x34' + b'com/iruen/shaded/asm/ClassReader\x00'

class Phase18GateTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='p18-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.jar=self.root/'agent.jar'
        with ZipFile(self.jar,'w') as archive:
            archive.writestr('META-INF/MANIFEST.MF',
                'Manifest-Version: 1.0\r\nPremain-Class: com.iruen.runtimesbom.RuntimeSbomAgent\r\nAgent-Class: com.iruen.runtimesbom.RuntimeSbomAgent\r\n')
            for name in AUDIT.EXPECTED:
                archive.writestr(name,HEADER)
        self.jdk=self.root/'jdk';self.jdk.mkdir()
        self.live=self.root/'live';self.live.mkdir()
        self.digest=AUDIT.audit(self.jar)['sha256']
    def test_structural_positive_does_not_approve(self):
        self.assertEqual(AUDIT.audit(self.jar)['status'],'PASS')
        report=GATE.accept(self.jar,self.jdk,self.live)
        self.assertEqual(report['stagingReview'],'HOLD')
        self.assertEqual(report['productionDeployment'],'HOLD')
    def test_reject_missing_shaded_class(self):
        bad=self.root/'bad.jar'
        with ZipFile(bad,'w') as archive:
            archive.writestr('META-INF/MANIFEST.MF','Premain-Class: com.iruen.runtimesbom.RuntimeSbomAgent')
        self.assertEqual(AUDIT.audit(bad)['status'],'FAIL')
    def test_reject_internal_asm_class(self):
        bad=self.root/'internal.jar'
        with ZipFile(bad,'w') as archive:
            archive.writestr('META-INF/MANIFEST.MF','Premain-Class: com.iruen.runtimesbom.RuntimeSbomAgent')
            for name in AUDIT.EXPECTED:
                archive.writestr(name,HEADER.replace(b'com/iruen/shaded/asm/',b'jdk/internal/org/objectweb/asm/'))
        self.assertEqual(AUDIT.audit(bad)['status'],'FAIL')
    def prepare(self, digest=None, source='OFFICIAL_SHADED_RUNTIME',tpsdelta=-3,p95delta=4):
        digest=digest or self.digest
        for v in (8,11,17,21):
            (self.jdk/('jdk-%d.json'%v)).write_text(json.dumps({'status':'PASS','evidenceMode':source,
                'jdkMajor':v,'officialJarSha256':digest,'methodEvidence':True,'artifactAudit':'PASS'}))
        for name in GATE.APPS:
            p=self.live/name;p.mkdir(exist_ok=True)
            (p/'summary.json').write_text(json.dumps({'status':'PASS','application':name,
             'evidenceType':'actual-live-was','evidenceMode':source,'officialJarSha256':digest,
             'modes':{'asm-traced':{'evidence':{'purlFound':True,'methodExecuted':True},
                                   'http':{'successTps':980}},
                      'baseline':{'http':{'successTps':1000}}},
             'comparison':{'tpsDeltaPercent':tpsdelta,'p95DeltaPercent':p95delta}}))
    def test_all_evidence_only_allows_staging_review(self):
        self.prepare()
        r=GATE.accept(self.jar,self.jdk,self.live)
        self.assertEqual(r['stagingReview'],'ELIGIBLE_FOR_HUMAN_REVIEW')
        self.assertEqual(r['productionDeployment'],'HOLD')
    def test_reject_wrong_artifact_digest(self):
        self.prepare(digest='0'*64)
        self.assertEqual(GATE.accept(self.jar,self.jdk,self.live)['stagingReview'],'HOLD')
    def test_reject_internal_asm_evidence(self):
        self.prepare(source='JDK21_INTERNAL_ASM_TEST')
        self.assertEqual(GATE.accept(self.jar,self.jdk,self.live)['stagingReview'],'HOLD')
    def test_reject_excess_performance_regression(self):
        self.prepare(tpsdelta=-30)
        self.assertEqual(GATE.accept(self.jar,self.jdk,self.live)['stagingReview'],'HOLD')
    def test_reject_missing_was(self):
        self.prepare()
        (self.live/'tomcat10'/'summary.json').unlink()
        self.assertEqual(GATE.accept(self.jar,self.jdk,self.live)['stagingReview'],'HOLD')

if __name__=='__main__':unittest.main()
