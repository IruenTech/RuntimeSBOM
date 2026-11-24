"""Release gate must not infer real WAS success from fixture-only diagnostics."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('gate',ROOT/'scripts/phase14-release-gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.th={'maxTpsDropPercent':10,'maxP95IncreasePercent':20}
        self.official={'version':'1.0.0-rc5','status':'PASS','evidenceType':'official-shaded-asm-executed',
                       'asmDependency':'org.ow2.asm:asm:9.7.1','agentClassMajorVersion':52,'workerMethodEntries':12}
        self.matrix={'version':'1.0.0-rc5','evidenceType':'multi-jdk-official',
                     'jdk':{x:'PASS' for x in ('8','11','17','21')}}
        self.apps={}
        for app in gate.APPS:
            self.apps[app]={'version':'1.0.0-rc5','status':'PASS','evidenceType':'actual-live-was',
                'application':app,'modes':{'baseline':{'http':{'requests':100,'errors':0,'successTps':100,'latencyMs':{'p95':10}}},
                          'asm-traced':{'http':{'requests':100,'errors':0,'successTps':95,'latencyMs':{'p95':11}},
                                        'evidence':{'purlFound':True,'methodExecuted':True}}}}

    def test_missing_data_is_hold(self):
        self.assertEqual(gate.gate(None,None,{},self.th)['releaseCandidateDecision'],'HOLD')

    def test_fixture_cannot_substitute_real_was(self):
        self.apps['tomcat9']['evidenceType']='real-HTTP-local-fixture'
        self.assertEqual(gate.gate(self.official,self.matrix,self.apps,self.th)['releaseCandidateDecision'],'HOLD')

    def test_dropped_request_fails(self):
        self.apps['spring-boot2']['modes']['asm-traced']['http']['errors']=1
        self.assertEqual(gate.gate(self.official,self.matrix,self.apps,self.th)['releaseCandidateDecision'],'HOLD')

    def test_tps_policy_fails(self):
        self.apps['tomcat10']['modes']['asm-traced']['http']['successTps']=50
        self.assertEqual(gate.gate(self.official,self.matrix,self.apps,self.th)['releaseCandidateDecision'],'HOLD')

    def test_all_checks_pass_staging_only(self):
        result=gate.gate(self.official,self.matrix,self.apps,self.th)
        self.assertEqual(result['releaseCandidateDecision'],'STAGING_RC_ELIGIBLE')
        self.assertEqual(result['productionDeploymentDecision'],'NOT_APPROVED')

if __name__=='__main__':unittest.main()
