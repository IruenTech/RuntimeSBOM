"""Stage29: fail-closed validation of trend analysis, provenance, and binary identity."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

p29=module('stage29_sustained','phase29-sustained.py')
lifecycle=module('stage29_lifecycle','phase29-was-lifecycle.py')
outage=module('stage29_outage','phase29-outage-replay.py')

class Phase29Tests(unittest.TestCase):
    def test_exact_official_binary(self):
        self.assertEqual(hashlib.sha256(lifecycle.JAR.read_bytes()).hexdigest(),lifecycle.SHA)
        self.assertEqual(p29.SHA,lifecycle.SHA)
        self.assertEqual(outage.SHA,lifecycle.SHA)

    def test_three_conditions_required(self):
        self.assertEqual(set(p29.MODES),{'baseline','loaded-only','asm-traced'})

    def test_window_summary(self):
        rows=[]
        for mode,tps,rss in [('baseline',1000,100),('loaded-only',980,120),('asm-traced',920,140)]:
            for n in (1,2,3):
                rows.append({'mode':mode,'window':n,'successTps':tps,'p95Ms':5,'p99Ms':9,
                             'errors':0,'rssKiB':rss+n*3,'cpuSecondsWindow':1.0})
        report=p29.summary(rows)
        self.assertEqual(report['comparison']['asmTpsDeltaPercent'],-8)
        self.assertEqual(report['asm-traced']['rssEndMinusStartKiB'],6)
        self.assertEqual(report['loaded-only']['windows'],3)

    def test_missing_window_fails(self):
        with self.assertRaises(ValueError):p29.summary([])

    def test_unknown_memory_measured_as_null(self):
        rows=[]
        for mode in p29.MODES:
            for n in (1,2):
                rows.append({'mode':mode,'window':n,'successTps':100,'p95Ms':1,'p99Ms':2,
                             'errors':0,'rssKiB':None,'cpuSecondsWindow':None})
        report=p29.summary(rows)
        self.assertIsNone(report['asm-traced']['rssEndMinusStartKiB'])
        self.assertEqual(report['asm-traced']['rssSamplesAvailable'],0)

    def make_bom(self,path,purl=True,executed=True,sha=True):
        props=[{'name':'runtimeSbom:classLoader','value':'loader@a'},
               {'name':'runtimeSbom:observedMethodEntryCount','value':'5' if executed else '0'},
               {'name':'runtimeSbom:runtimeEvidenceState','value':'METHOD_EXECUTED' if executed else 'CLASS_LOADED'}]
        path.write_text(json.dumps({'bomFormat':'CycloneDX','components':[{'name':'commons-lang3',
          'purl':lifecycle.PURL if purl else None,'properties':props,
          'hashes':[{'alg':'SHA-256','content':'a'*64}] if sha else []}]}))

    def test_real_method_provenance_positive(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.json';self.make_bom(p)
            self.assertEqual(lifecycle.evidence(p)[0]['observedMethodEntries'],5)

    def test_missing_purl_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.json';self.make_bom(p,purl=False)
            with self.assertRaises(RuntimeError):lifecycle.evidence(p)

    def test_loaded_only_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.json';self.make_bom(p,executed=False)
            with self.assertRaises(RuntimeError):lifecycle.evidence(p)

    def test_missing_sha_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.json';self.make_bom(p,sha=False)
            with self.assertRaises(RuntimeError):lifecycle.evidence(p)

    def test_invalid_bom_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.json';p.write_text(json.dumps({'bomFormat':'Other'}))
            with self.assertRaises(RuntimeError):lifecycle.evidence(p)

if __name__=='__main__':unittest.main()

class Phase29ReviewGateTests(unittest.TestCase):
    def setUp(self):
        self.review=module('stage29review','phase29-review-gate.py')
        self.local={'phase':29,'status':'PASS','checks':[
            {'name':n,'status':'PASS'} for n in
            ('phase29_unit_tests','phase29_outage_backlog_replay','phase29_windowed_http','collector_regression')]}
        self.live={}
        for app in self.review.APPS:
            item={'purl':lifecycle.PURL,'sha256':'a'*64,'observedMethodEntries':2}
            cycles=[{'cycle':1,'pid':123,'executionEvidence':[item]},
                    {'cycle':2,'pid':124,'executionEvidence':[item],'newLoaderIds':['loader-b']}]
            self.live[app]={'stage':29,'app':app,'status':'PASS','agentSha256':self.review.SHA,'cycles':cycles}

    def test_all_proof_required_for_human_review(self):
        actual=self.review.verify(self.local,self.live)
        self.assertEqual(actual['stagingReview'],'ELIGIBLE_FOR_HUMAN_REVIEW')
        self.assertEqual(actual['productionDeployment'],'HOLD')

    def test_missing_tomcat_fails_closed(self):
        del self.live['tomcat10']
        self.assertIn('MISSING_tomcat10',self.review.verify(self.local,self.live)['failures'])

    def test_sha_mismatch_fails_closed(self):
        self.live['spring-boot3']['agentSha256']='b'*64
        self.assertIn('INVALID_spring-boot3',self.review.verify(self.local,self.live)['failures'])

    def test_missing_redeploy_loader_fails_closed(self):
        del self.live['tomcat9']['cycles'][1]['newLoaderIds']
        self.assertIn('NO_NEW_CLASSLOADER_tomcat9',self.review.verify(self.local,self.live)['failures'])

    def test_no_restart_fails_closed(self):
        self.live['spring-boot2']['cycles'][1]['pid']=123
        self.assertIn('NO_JVM_RESTART_spring-boot2',self.review.verify(self.local,self.live)['failures'])

class Phase29ExactArchiveTests(unittest.TestCase):
    def test_mismatched_actual_jar_sha_is_rejected(self):
        with self.assertRaises(RuntimeError):
            lifecycle.assert_exact_dependency_evidence([{'sha256':'bad'}],'a'*64)

    def test_matching_actual_jar_sha_is_accepted(self):
        lifecycle.assert_exact_dependency_evidence([{'sha256':'a'*64}],'a'*64)
