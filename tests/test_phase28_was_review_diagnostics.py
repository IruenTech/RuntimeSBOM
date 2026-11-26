import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

M=Path(__file__).resolve().parents[1]/'scripts/phase28-was-review-diagnostics.py'
spec=importlib.util.spec_from_file_location('diag',M)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def sample():
    modes={k:{'http':{'successTps':1234.,'errorRate':0,
                      'latencyMs':{'p95':3.1}},
              'evidence':{'methodExecuted':False,'purlFound':True}} for k in ('baseline','loaded-only','asm-traced')}
    modes['asm-traced']['evidence']['methodExecuted']=True
    return {'status':'PASS','application':'spring-boot2',
            'evidenceMode':'OFFICIAL_SHADED_RUNTIME','officialJarSha256':'a'*64,
            'archiveEvidenceMatches':True,'applicationArchiveSha256':'b'*64,
            'embeddedDependencySha256':'c'*64,'httpModes':modes,
            'comparison':{'tpsDeltaPercent':-2.0,'p95DeltaPercent':3.0}}


class TestReviewDiagnostics(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'phase21-summary.json'
    def tearDown(self):self.tmp.cleanup()
    def call(self,obj):
        self.path.write_text(json.dumps(obj),encoding='utf-8')
        return mod.evaluate('spring-boot2',self.path)
    def test_valid(self):self.assertEqual(self.call(sample())['status'],'DIAGNOSTIC_CHECKS_PASS')
    def test_missing_summary(self):self.assertIn('summaryReadable',mod.evaluate('spring-boot2',self.path)['checks'])
    def test_slow_tps(self):
        d=sample();d['comparison']['tpsDeltaPercent']=-16
        self.assertFalse(self.call(d)['checks']['tpsSlo'])
    def test_high_p95(self):
        d=sample();d['comparison']['p95DeltaPercent']=26
        self.assertFalse(self.call(d)['checks']['p95Slo'])
    def test_missing_purl(self):
        d=sample();d['httpModes']['asm-traced']['evidence']['purlFound']=False
        self.assertFalse(self.call(d)['checks']['asmPurlFound'])
    def test_missing_execution(self):
        d=sample();d['httpModes']['asm-traced']['evidence']['methodExecuted']=False
        self.assertFalse(self.call(d)['checks']['asmMethodExecuted'])
    def test_wrong_agent(self):
        d=sample();d['officialJarSha256']='x'
        self.assertFalse(self.call(d)['checks']['officialJarShaPresent'])
    def test_wrong_archive(self):
        d=sample();d['archiveEvidenceMatches']=False
        self.assertFalse(self.call(d)['checks']['archiveEvidenceMatches'])
    def test_invalid_app(self):
        d=sample();d['application']='spring-boot3'
        self.assertFalse(self.call(d)['checks']['applicationMatches'])
    def test_nan_deltas(self):
        d=sample();d['comparison']['tpsDeltaPercent']=float('nan')
        self.assertFalse(self.call(d)['checks']['tpsDeltaPresent'])
    def test_loading_false_positive(self):
        d=sample();d['httpModes']['loaded-only']['evidence']['methodExecuted']=True
        self.assertFalse(self.call(d)['checks']['loadingOnlyNoMethodExecuted'])
    def test_missing_tps(self):
        d=sample();del d['httpModes']['baseline']['http']['successTps']
        self.assertFalse(self.call(d)['checks']['baselineHttpSuccess'])

if __name__=='__main__':unittest.main()
