"""Mutation and negative controls for independent fixture accuracy scoring."""
import copy
import importlib.util
import unittest
from pathlib import Path

PATH=Path(__file__).resolve().parent.parent/'scripts/phase20-accuracy.py'
spec=importlib.util.spec_from_file_location('phase20_accuracy',PATH)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
PURL='pkg:maven/com.example.fixture/a@1.0'
SHA='a'*64

def component(purl=PURL, sha=SHA, source='file:/tmp/test-fixture.jar', loader='L1', calls=3, state='METHOD_EXECUTED'):
    return {'type':'library','purl':purl,'hashes':[{'alg':'SHA-256','content':sha}],
            'properties':[{'name':'runtimeSbom:source','value':source},
                          {'name':'runtimeSbom:classLoader','value':loader},
                          {'name':'runtimeSbom:observedMethodEntryCount','value':str(calls)},
                          {'name':'runtimeSbom:runtimeEvidenceState','value':state}]}

TRUTH={'name':'accuracy-unit','scopeTerms':['fixture','pkg:maven/com.example.fixture/'],
       'groundTruthSource':'test fixture provided independently',
       'expected':[{'purl':PURL,'sha256':SHA,'sourceSuffix':'test-fixture.jar',
                    'methodEntries':3,'evidenceState':'METHOD_EXECUTED'}]}

def doc(items, unattributed=0):
    return {'bomFormat':'CycloneDX','specVersion':'1.6','components':items,
            'metadata':{'properties':[{'name':'runtimeSbom:unattributedMethodEntries','value':str(unattributed)}]}}

class AccuracyTest(unittest.TestCase):
    def test_exact_pass(self):
        self.assertTrue(module.evaluate(TRUTH,doc([component()]))['strictFixturePass'])
    def test_missing_component_recall(self):
        x=module.evaluate(TRUTH,doc([]))
        self.assertEqual((x['truePositives'],x['falseNegatives'],x['identityRecall']),(0,1,0))
        self.assertFalse(x['strictFixturePass'])
    def test_extra_component_precision(self):
        x=module.evaluate(TRUTH,doc([component(),component(source='file:/tmp/other-fixture.jar',loader='L2')]))
        self.assertEqual((x['truePositives'],x['falsePositives']), (1,1))
        self.assertEqual(x['identityPrecision'],0.5)
    def test_wrong_sha_is_not_accepted(self):
        x=module.evaluate(TRUTH,doc([component(sha='b'*64)]))
        self.assertEqual((x['truePositives'],x['falsePositives'],x['falseNegatives']),(0,1,1))
    def test_wrong_purl_is_not_accepted(self):
        x=module.evaluate(TRUTH,doc([component(purl='pkg:maven/malicious/wrong@2.0')]))
        self.assertEqual((x['truePositives'],x['falsePositives'],x['falseNegatives']),(0,1,1))
    def test_wrong_source_is_not_accepted(self):
        x=module.evaluate(TRUTH,doc([component(source='file:/tmp/other-fixture.jar')]))
        self.assertEqual((x['truePositives'],x['falsePositives'],x['falseNegatives']),(0,1,1))
    def test_wrong_execution_evidence_is_not_accepted(self):
        x=module.evaluate(TRUTH,doc([component(calls=0,state='CLASS_LOADED')]))
        self.assertEqual(x['identityPrecision'],1.0)
        self.assertFalse(x['executionEvidenceExact'])
        self.assertFalse(x['strictFixturePass'])
    def test_duplicate_loader_token_is_not_accepted(self):
        tr=copy.deepcopy(TRUTH);tr['expected'].append(copy.deepcopy(tr['expected'][0]))
        tr['expected'][1]['methodEntries']=2
        x=module.evaluate(tr,doc([component(),component(calls=2)]))
        self.assertEqual(x['identityRecall'],1.0)
        self.assertFalse(x['classLoaderTokensDistinct'])
    def test_distinct_loader_token_and_counts_are_accepted(self):
        tr=copy.deepcopy(TRUTH);tr['expected'].append(copy.deepcopy(tr['expected'][0]))
        tr['expected'][1]['methodEntries']=2
        x=module.evaluate(tr,doc([component(),component(loader='L2',calls=2)]))
        self.assertTrue(x['strictFixturePass'])
    def test_unattributed_calls_fail_strict_mode(self):
        x=module.evaluate(TRUTH,doc([component()],unattributed=5))
        self.assertFalse(x['strictFixturePass'])
    def test_forged_manifest_cannot_easily_pass(self):
        x=module.evaluate(TRUTH,doc([component(sha='x'*64,loader='')]))
        self.assertFalse(x['strictFixturePass'])
    def test_invalid_truth_or_sbom_is_rejected(self):
        with self.assertRaises(ValueError):module.evaluate({'expected':[]},doc([]))
        with self.assertRaises(ValueError):module.evaluate(TRUTH,{'bomFormat':'not CycloneDX'})

if __name__=='__main__':unittest.main()
