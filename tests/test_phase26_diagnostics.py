import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('phase26_ci_diag',ROOT/'scripts/phase26-ci-diagnostics.py')
d=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=d
spec.loader.exec_module(d)

PURL='pkg:maven/org.apache.commons/commons-lang3@3.14.0'

def component(purl=PURL, state='METHOD_EXECUTED', count=7):
    return {'name':'commons-lang3','purl':purl,'properties':[
        {'name':'runtimeSbom:source','value':'jar:nested:/tmp/app.jar/!BOOT-INF/lib/commons-lang3-3.14.0.jar!/'},
        {'name':'runtimeSbom:runtimeEvidenceState','value':state},
        {'name':'runtimeSbom:observedMethodEntryCount','value':str(count)}]}

class TestPhase26Diagnostics(unittest.TestCase):
    def test_successful_runtime_purl_and_method(self):
        self.assertEqual(d.evidence_diagnostic({'components':[component()]})['status'],'PASS')
    def test_user_reported_nested_purl_missing(self):
        r=d.evidence_diagnostic({'components':[component(purl=None, count=65526)]})
        self.assertEqual(r['codes'],['MISSING_PURL'])
        self.assertEqual(r['metadataOrInstrumentationRootCause'],'PURL_METADATA')
    def test_method_missing_when_purl_present(self):
        r=d.evidence_diagnostic({'components':[component(state='CLASS_LOADED',count=0)]})
        self.assertEqual(r['codes'],['MISSING_METHOD_EXECUTION'])
    def test_method_hits_zero_when_state_claims_executed(self):
        r=d.evidence_diagnostic({'components':[component(count=0)]})
        self.assertEqual(r['status'],'FAIL')
    def test_diagnostics_redacts_maven_credentials(self):
        sample='[ERROR] Could not resolve artifact from https://user:verysecret@repo.example.org/ Maven password=secret'
        result=d.classify_text(sample)
        text=' '.join(result['mavenErrorExcerpts'])
        self.assertNotIn('verysecret',text)
        self.assertNotIn('password=secret',text)
    def test_maven_compile_issue(self):
        x=d.classify_text('[ERROR] COMPILATION ERROR: cannot find symbol')
        self.assertIn('JAVA_COMPILATION',[e['code'] for e in x['codes']])
    def test_jdk_compatibility_issue(self):
        x=d.classify_text('[ERROR] invalid target release: 21')
        self.assertIn('JDK_COMPATIBILITY',[e['code'] for e in x['codes']])
    def test_dependency_network_issue(self):
        x=d.classify_text('[ERROR] Non-resolvable parent POM: UnknownHostException')
        codes=[e['code'] for e in x['codes']]
        self.assertIn('DEPENDENCY_OR_PLUGIN',codes)
        self.assertIn('DNS_OR_TLS',codes)
    def test_spring_boot2_build_failure_log_was_suppressed(self):
        x=d.classify_text('[ERROR] Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin: Compilation failure')
        self.assertIn('JAVA_COMPILATION',[e['code'] for e in x['codes']])
    def test_success_is_not_inferred_from_missing_log(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(d.inspect_file(Path(t)/'build.log')['classification'],'MISSING_LOG')
    def test_maven_success_marker(self):
        self.assertEqual(d.classify_text('[INFO] BUILD SUCCESS')['classification'],'BUILD_SUCCESS')
    def test_report_preserves_sha_and_does_not_claim_release(self):
        with tempfile.TemporaryDirectory() as t:
            log=Path(t)/'build.log';log.write_text('[ERROR] COMPILATION ERROR')
            r=d.write_report([log])
            self.assertEqual(r['productionDeployment'],'HOLD')
            self.assertEqual(len(r['logs'][0]['sha256']),64)
    def test_real_server_log_without_errors_not_official_pass(self):
        self.assertEqual(d.classify_text('[RuntimeSBOM] wrote 33 provenance sources')['classification'],'INCONCLUSIVE')
    def test_workflow_contract(self):
        w=(ROOT/'.github/workflows/phase26-staging.yml').read_text()
        for x in ('official-build:', 'jdk-matrix:', 'was-matrix:', 'review:', 'boot2-build-isolation:',
                  'phase26-ci-diagnostics.py','phase21-staging-live.py',
                  'spring-boot2', 'spring-boot3','tomcat9','tomcat10',
                  "jdk: ['8', '11', '17', '21']"):
            self.assertIn(x,w)
        self.assertNotIn('kubectl apply',w)
    def test_ci_review_rejects_failed_child_job(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('review_stage25',ROOT/'scripts/phase25-review.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        jobs={x:{'result':'success'} for x in ('official-build','boot2-build-isolation','jdk-matrix','was-matrix')}
        jobs['boot2-build-isolation']={'result':'failure'}
        report=module.evaluate({'stagingReview':'ELIGIBLE_FOR_HUMAN_REVIEW','officialJarSha256':'test'},None,jobs)
        self.assertEqual(report['stagingReview'],'HOLD')
        self.assertIn('boot2-build-isolation',' '.join(report['blockingReasons']))
    def test_ci_review_all_success_still_requires_human(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('review_stage25',ROOT/'scripts/phase25-review.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        jobs={x:{'result':'success'} for x in ('official-build','boot2-build-isolation','jdk-matrix','was-matrix')}
        report=module.evaluate({'stagingReview':'ELIGIBLE_FOR_HUMAN_REVIEW','officialJarSha256':'test'},None,jobs)
        self.assertEqual(report['stagingReview'],'ELIGIBLE_FOR_HUMAN_REVIEW')
        self.assertEqual(report['productionDeployment'],'HOLD')
    def test_ci_review_missing_child_job_blocks(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('review_stage25',ROOT/'scripts/phase25-review.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        report=module.evaluate({'stagingReview':'ELIGIBLE_FOR_HUMAN_REVIEW'},None,{'official-build':{'result':'success'}})
        self.assertEqual(report['stagingReview'],'HOLD')
    def test_boot3_hotfix_present(self):
        source=(ROOT/'src/main/java/com/iruen/runtimesbom/JarMetadata.java').read_text()
        self.assertIn('normalizeArchiveLocation',source)
        self.assertIn('nested:',source)

if __name__=='__main__':unittest.main()
