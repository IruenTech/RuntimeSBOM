"""Independent safety/fail-closed tests for the Phase 21 archive validator."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('archive21',ROOT/'scripts/phase21-archive-evidence.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Phase21ArtifactEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.archive=Path(self.tmp.name)/'demo.jar'
        self.lib=b'fake-only-dependency-bytes-unit-test'
        with ZipFile(self.archive,'w') as z:
            z.writestr('BOOT-INF/lib/commons-lang3-3.14.0.jar',self.lib)
        self.sha=hashlib.sha256(self.lib).hexdigest()
        self.purl=module.PURL
        self.sbom={'bomFormat':'CycloneDX','specVersion':'1.6','components':[self.component()]}

    def component(self):
        return {'type':'library','name':'commons-lang3','purl':module.PURL,
                'hashes':[{'alg':'SHA-256','content':self.sha}],
                'properties':[
                  {'name':'runtimeSbom:source','value':'jar:file:/app.jar!/BOOT-INF/lib/commons-lang3-3.14.0.jar!/'},
                  {'name':'runtimeSbom:classLoader','value':'loader-a'},
                  {'name':'runtimeSbom:runtimeEvidenceState','value':'METHOD_EXECUTED'},
                  {'name':'runtimeSbom:observedMethodEntryCount','value':'12'}]}

    def replace(self,name,value):
        for prop in self.sbom['components'][0]['properties']:
            if prop['name']==name:prop['value']=value

    def verify(self,mode='asm-traced'):
        return module.verify(self.archive,self.sbom,mode)

    def test_exact_identity_and_execution(self):
        report=self.verify()
        self.assertEqual(report['status'],'PASS')
        self.assertEqual(report['expected']['dependencySha256'],self.sha)

    def test_wrong_sha_rejected(self):
        self.sbom['components'][0]['hashes'][0]['content']='0'*64
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_wrong_purl_rejected(self):
        self.sbom['components'][0]['purl']='pkg:maven/not/real@1.0'
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_empty_loader_rejected(self):
        self.replace('runtimeSbom:classLoader','')
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_source_disagree_rejected(self):
        self.replace('runtimeSbom:source','/webapps/unrelated.jar')
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_missing_execution_rejected(self):
        self.replace('runtimeSbom:runtimeEvidenceState','CLASS_LOADED')
        self.replace('runtimeSbom:observedMethodEntryCount','0')
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_loaded_only_exact(self):
        self.replace('runtimeSbom:runtimeEvidenceState','CLASS_LOADED')
        self.replace('runtimeSbom:observedMethodEntryCount','0')
        self.assertEqual(self.verify('loaded-only')['status'],'PASS')

    def test_loading_only_false_execution_rejected(self):
        self.assertEqual(self.verify('loaded-only')['status'],'FAIL')

    def test_duplicate_purl_source_rejected(self):
        self.sbom['components'].append(self.component())
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_missing_or_double_nested_jar_rejected(self):
        with ZipFile(self.archive,'w') as z:z.writestr('random.txt',b'test')
        with self.assertRaises(ValueError):self.verify()
        with ZipFile(self.archive,'w') as z:
            z.writestr('BOOT-INF/lib/commons-lang3-3.14.0.jar',self.lib)
            z.writestr('WEB-INF/lib/commons-lang3-3.14.0.jar',self.lib)
        with self.assertRaises(ValueError):self.verify()

    def test_malformed_count_rejected(self):
        self.replace('runtimeSbom:observedMethodEntryCount','NaN')
        self.assertEqual(self.verify()['status'],'FAIL')

if __name__=='__main__':unittest.main()
