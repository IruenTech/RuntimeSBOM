import copy
import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('quality',ROOT/'scripts/phase23-sbom-quality.py')
quality=importlib.util.module_from_spec(spec);spec.loader.exec_module(quality)

def prop(name,val):return {'name':'runtimeSbom:'+name,'value':str(val)}
def fixture(mode='METHOD_ENTRY_REQUESTED',state='OBSERVED_PARTIAL',hits=5):
    return {'bomFormat':'CycloneDX','specVersion':'1.6','metadata':{'properties':[
        prop('traceMode',mode),prop('observationQuality',state),prop('observationLimitations','OBSERVED_DOES_NOT_PROVE_COMPLETE'),
        prop('attributedMethodEntries',hits),prop('unattributedMethodEntries',0),prop('invalidMethodEventKeys',0),
        prop('transformFailures',0),prop('classLoaderIsolated',0),prop('registrationDrops',0),
        prop('droppedEvents',0),prop('traceDisabled','false'),prop('sampleEvery',1)]},
        'components':[{'properties':[prop('runtimeEvidenceState','METHOD_EXECUTED' if hits else 'CLASS_LOADED'),prop('observedMethodEntryCount',hits)]}]}

class QualityTests(unittest.TestCase):
    def test_observed_positive(self):self.assertEqual(quality.assess(fixture(),True)['status'],'PASS')
    def test_mismatch_state(self):
        f=fixture(state='OBSERVED_PARTIAL');f['metadata']['properties'][0]['value']='LOADING_ONLY'
        self.assertEqual(quality.assess(f)['status'],'FAIL')
    def test_no_invented_execution(self):
        f=fixture(mode='LOADING_ONLY',state='LOADING_ONLY',hits=5)
        self.assertEqual(quality.assess(f)['status'],'FAIL')
    def test_counter_mismatch(self):
        f=fixture();f['components'][0]['properties'][1]['value']='2'
        self.assertEqual(quality.assess(f)['status'],'FAIL')
    def test_malformed_bom(self):self.assertEqual(quality.assess({})['status'],'FAIL')
    def test_no_hits_not_method_proof(self):
        f=fixture(state='NO_METHOD_HITS',hits=0)
        self.assertEqual(quality.assess(f,True)['status'],'FAIL')
        self.assertEqual(quality.assess(f)['status'],'PASS')
    def test_sampling(self):
        f=fixture(state='SAMPLED');f['metadata']['properties'][-1]['value']='10'
        self.assertEqual(quality.assess(f)['status'],'PASS')
    def test_isolated_loader_degraded(self):
        f=fixture(state='DEGRADED')
        for p in f['metadata']['properties']:
            if p['name']=='runtimeSbom:classLoaderIsolated':p['value']='1'
        self.assertEqual(quality.assess(f, True)['status'],'PASS')
        f['metadata']['properties'][1]['value']='OBSERVED_PARTIAL'
        self.assertEqual(quality.assess(f)['status'],'FAIL')
    def test_unattributed_entries_degraded(self):
        f=fixture(state='DEGRADED')
        for p in f['metadata']['properties']:
            if p['name']=='runtimeSbom:unattributedMethodEntries':p['value']='6'
        self.assertEqual(quality.assess(f)['status'],'PASS')
    def test_missing_signal_rejected(self):
        f=fixture();f['metadata']['properties'].pop()
        self.assertEqual(quality.assess(f)['status'],'FAIL')
    def test_duplicate_signal_rejected(self):
        f=fixture();f['metadata']['properties'].append(copy.deepcopy(f['metadata']['properties'][0]))
        self.assertEqual(quality.assess(f)['status'],'FAIL')
    def test_false_component_exec_state_rejected(self):
        f=fixture();f['components'][0]['properties'][0]['value']='CLASS_LOADED'
        self.assertEqual(quality.assess(f)['status'],'FAIL')
if __name__=='__main__':unittest.main()
