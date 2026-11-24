"""Negative/functional tests for Phase 25 build failure diagnostics and review gates."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent.parent

def load(path,identifier):
    spec=importlib.util.spec_from_file_location(identifier,ROOT/'scripts'/path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

preflight=load('phase25-build-preflight.py','phase25preflight')
diagnostic=load('phase25-ci-diagnose.py','phase25diagnostics')
review=load('phase25-review.py','phase25review')

class BuildPreflight(unittest.TestCase):
    def test_official_asm_java8_shading_configuration(self):
        self.assertTrue(all(preflight.check_pom(ROOT/'pom.xml').values()))
    def test_rejects_wrong_asm_version(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'pom.xml';p.write_text((ROOT/'pom.xml').read_text().replace('<version>9.7.1</version>','<version>9.6</version>'))
            self.assertFalse(preflight.check_pom(p)['explicitOfficialAsm971'])
    def test_rejects_missing_shading(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'pom.xml';p.write_text((ROOT/'pom.xml').read_text().replace('<shadedPattern>com.iruen.shaded.asm</shadedPattern>','<shadedPattern>com.example.unrelated</shadedPattern>'))
            self.assertFalse(preflight.check_pom(p)['shadingRelocation'])
    def test_fails_closed_when_maven_missing(self):
        with patch.object(preflight.shutil,'which',side_effect=lambda x: None if x=='mvn' else '/usr/bin/java'):
            r=preflight.execute(require_toolchain=True)
        self.assertEqual(r['status'],'HOLD')
        self.assertFalse(r['officialMavenBuildExecuted'])
    def test_does_not_claim_deployment_if_maven_installed(self):
        with patch.object(preflight.shutil,'which',side_effect=lambda x: '/usr/bin/true'):
            r=preflight.execute(require_toolchain=True)
        self.assertEqual(r['status'],'READY_FOR_OFFICIAL_BUILD')
        self.assertEqual(r['productionDeployment'],'HOLD')

class FailureDiagnostics(unittest.TestCase):
    def test_dns_failure_classification(self):
        self.assertIn('NETWORK_DNS',[x['code'] for x in diagnostic.diagnose('curl: (6) Could not resolve host: repo.maven.apache.org')['diagnoses']])
    def test_maven_artifact_resolution(self):
        self.assertIn('MAVEN_DEPENDENCY',[x['code'] for x in diagnostic.diagnose('Failed to collect dependencies org.ow2.asm:asm:9.7.1')['diagnoses']])
    def test_unsupported_bytecode(self):
        self.assertIn('JAVA_RELEASE',[x['code'] for x in diagnostic.diagnose('java.lang.UnsupportedClassVersionError: abc class has been compiled by a more recent version')['diagnoses']])
    def test_class_linkage(self):
        self.assertIn('ASM_LINKAGE',[x['code'] for x in diagnostic.diagnose('java.lang.NoClassDefFoundError: org/objectweb/asm/ClassReader')['diagnoses']])
    def test_method_verification(self):
        self.assertIn('BYTECODE_VERIFICATION',[x['code'] for x in diagnostic.diagnose('java.lang.VerifyError: Expecting a stackmap frame')['diagnoses']])
    def test_artifact_sha_mismatch(self):
        self.assertIn('ARTIFACT_IDENTITY',[x['code'] for x in diagnostic.diagnose('SHA-256 mismatch: expected X got Y')['diagnoses']])
    def test_diagnostics_do_not_copy_log_raw_text(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'build.log';p.write_text('secret_super_sensitive_password=abc\nCould not resolve host repo.maven.apache.org')
            r=diagnostic.evaluate([p])
            self.assertNotIn('secret_super_sensitive_password',json.dumps(r))
            self.assertEqual(r['status'],'ISSUES_IDENTIFIED')
    def test_missing_log_not_success(self):
        self.assertEqual(diagnostic.evaluate([Path('/nonexistent-unlikely-50182')])['inputs'][0]['status'],'MISSING_LOG')

class ReviewTests(unittest.TestCase):
    def test_missing_staging_is_hold(self):
        r=review.evaluate(None)
        self.assertEqual(r['stagingReview'],'HOLD')
        self.assertEqual(r['productionDeployment'],'HOLD')
    def test_valid_staging_only_enables_human_review(self):
        r=review.evaluate({'stagingReview':'ELIGIBLE_FOR_HUMAN_REVIEW','officialJarSha256':'a'*64})
        self.assertEqual(r['stagingReview'],'ELIGIBLE_FOR_HUMAN_REVIEW')
        self.assertEqual(r['productionDeployment'],'HOLD')
    def test_diagnostic_blocks_synthetic_eligibility(self):
        r=review.evaluate({'stagingReview':'ELIGIBLE_FOR_HUMAN_REVIEW'},
              {'inputs':[{'diagnoses':[{'code':'MAVEN_DEPENDENCY','recommendedAction':'Verify cache'}]}]})
        self.assertEqual(r['stagingReview'],'HOLD')
    def test_official_build_pipeline_is_primary_workflow(self):
        text=(ROOT/'.github/workflows/phase25-official-asm.yml').read_text()
        self.assertIn('phase25-build-preflight.py --require-toolchain',text)
        self.assertIn('phase25-ci-diagnose.py',text)
        self.assertIn('phase25-review.py',text)
        self.assertIn('phase21-staging-live.py',text)
        self.assertIn("jdk: ['8', '11', '17', '21']",text)
        self.assertNotIn('kubectl apply',text)
        prior=(ROOT/'.github/workflows/phase24-official-asm-staging.yml').read_text()
        self.assertNotIn('  push:',prior)

if __name__=='__main__':unittest.main()
