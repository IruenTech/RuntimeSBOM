import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'

def import_script(filename):
    spec=importlib.util.spec_from_file_location('module_'+filename.replace('-','_'),SCRIPT/filename)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

probe=import_script('phase30-tomcat-retention.py')
review=import_script('phase30-review-gate.py')

class HistogramTests(unittest.TestCase):
    def test_one_reachable_loader(self):
        x=' num     #instances     #bytes  class name\n   1:  1   2048 org.apache.catalina.loader.ParallelWebappClassLoader\n'
        self.assertEqual(probe.count_webapp_loaders(x),1)
    def test_two_reachable_loaders(self):
        x=' 9:  2   222 org.apache.catalina.loader.ParallelWebappClassLoader\n'
        self.assertEqual(probe.count_webapp_loaders(x),2)
    def test_missing_loader_ignored(self):
        self.assertEqual(probe.count_webapp_loaders(' 1: 3 1000 java.lang.String'),0)
    def test_metaspace_nmt_parse(self):
        self.assertEqual(probe.metaspace_committed_kb(' - Metaspace (reserved=65536KB, committed=2832KB)'),2832)
    def test_missing_nmt_not_invented(self):
        self.assertIsNone(probe.metaspace_committed_kb('Native memory tracking is not enabled'))

class NmtCompatibilityTests(unittest.TestCase):
    JDK11_NMT = """1100:
Native Memory Tracking:
Total: reserved=2400000KB, committed=150000KB
-                     Class (reserved=1056874KB, committed=4970KB)
                            (classes #478)
                            (  Metadata:   )
                            (    reserved=8192KB, committed=4352KB)
                            (    used=3962KB)
                            (  Class space:)
                            (    reserved=1048576KB, committed=512KB)
"""
    JDK21_NMT = """Native Memory Tracking:
-                     Class (reserved=1048649KB, committed=201KB)
                            (  Metadata:   )
                            (    reserved=65536KB, committed=192KB)
-                 Metaspace (reserved=65548KB, committed=204KB)
                            (mmap: reserved=65536KB, committed=192KB)
"""
    def test_jdk11_metadata_fallback_is_not_class_total(self):
        self.assertEqual(probe.metaspace_metric(self.JDK11_NMT),(4352,'NMT_CLASS_METADATA'))
        self.assertEqual(probe.metaspace_committed_kb(self.JDK11_NMT),4352)
    def test_modern_top_level_preferred(self):
        self.assertEqual(probe.metaspace_metric(self.JDK21_NMT),(204,'NMT_METASPACE_CATEGORY'))
    def test_nmt_disabled_returns_no_fabricated_metric(self):
        self.assertEqual(probe.metaspace_metric('Native memory tracking is not enabled'),(None,'NMT_DISABLED'))
    def test_missing_metadata_fails_closed(self):
        self.assertEqual(probe.metaspace_metric('- Class (reserved=1056874KB, committed=4970KB)'),
                         (None,'NMT_FORMAT_UNRECOGNIZED'))
    def test_class_space_not_misinterpreted_as_metadata(self):
        text='(  Metadata:   )\n(no counters available)\n(  Class space:)\n(reserved=50KB, committed=32KB)'
        self.assertIsNone(probe.metaspace_committed_kb(text))
    def test_snapshot_source_and_raw_nmt_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            fake_hist='   1:   1   2048 org.apache.catalina.loader.ParallelWebappClassLoader\n'
            with patch.object(probe,'jcmd',side_effect=['GC.run completed',fake_hist,self.JDK11_NMT]):
                record=probe.sample(999,Path(d),2)
            self.assertEqual(record['metaspaceCommittedKiB'],4352)
            self.assertEqual(record['metaspaceMetricSource'],'NMT_CLASS_METADATA')
            self.assertEqual(record['reachableWebappClassLoaderInstances'],1)
            self.assertIn('Metadata:',(Path(d)/'nmt-02.txt').read_text())

class ReviewTests(unittest.TestCase):
    SHA='a'*64
    def report(self):
        data={'status':'PASS','agentSha256':self.SHA,'cyclesCompleted':6,
              'snapshots':[{'newLoaderIds':['loader'+str(i)],'methodEntriesForNewLoader':10,
                            'reachableWebappClassLoaderInstances':1,'gcCommandSucceeded':True,'metaspaceCommittedKiB':1000+i}
                           for i in range(6)],'failures':[]}
        return {app:json.loads(json.dumps(data)) for app in review.APPS}
    def phase29(self):return {'stagingReview':'ELIGIBLE_FOR_HUMAN_REVIEW','agentSha256':self.SHA}
    def test_success_is_human_review_only(self):
        out=review.decision(self.phase29(),self.report(),self.SHA)
        self.assertEqual(out['stagingReview'],'ELIGIBLE_FOR_HUMAN_REVIEW')
        self.assertEqual(out['productionDeployment'],'HOLD')
    def test_missing_probe_holds(self):
        self.assertEqual(review.decision(self.phase29(),{},self.SHA)['stagingReview'],'HOLD')
    def test_sha_mismatch_holds(self):
        self.assertEqual(review.decision(self.phase29(),self.report(),'b'*64)['stagingReview'],'HOLD')
    def test_old_loader_still_reachable_holds(self):
        d=self.report();d['tomcat10']['snapshots'][3]['reachableWebappClassLoaderInstances']=2
        self.assertIn('GC_REACHABILITY_NOT_ESTABLISHED_TOMCAT10',review.decision(self.phase29(),d,self.SHA)['failures'])
    def test_missing_nmt_holds(self):
        d=self.report();d['tomcat9']['snapshots'][3]['metaspaceCommittedKiB']=None
        self.assertEqual(review.decision(self.phase29(),d,self.SHA)['stagingReview'],'HOLD')
    def test_too_few_cycles_holds(self):
        d=self.report();d['tomcat9']['snapshots']=d['tomcat9']['snapshots'][:2];d['tomcat9']['cyclesCompleted']=2
        self.assertEqual(review.decision(self.phase29(),d,self.SHA)['stagingReview'],'HOLD')
    def test_missing_execution_evidence_holds(self):
        d=self.report();d['tomcat9']['snapshots'][0]['methodEntriesForNewLoader']=0
        self.assertEqual(review.decision(self.phase29(),d,self.SHA)['stagingReview'],'HOLD')

if __name__=='__main__':unittest.main()
