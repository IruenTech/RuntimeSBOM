import importlib.util
import sys
import unittest
from pathlib import Path
R=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('ci_contract',R/'scripts/phase24-ci-contract.py')
mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)

class WorkflowTests(unittest.TestCase):
    def test_current_workflow_passes_contract(self):
        self.assertEqual(mod.audit((R/'.github/workflows/phase24-official-asm-staging.yml').read_text())['status'],'PASS')
    def test_missing_official_build_is_rejected(self):
        text=(R/'.github/workflows/phase24-official-asm-staging.yml').read_text().replace('phase22-official-build.sh','echo fake build')
        self.assertEqual(mod.audit(text)['status'],'FAIL')
    def test_missing_real_was_is_rejected(self):
        text=(R/'.github/workflows/phase24-official-asm-staging.yml').read_text().replace('phase21-staging-live.py','phase21-synthetic.py')
        self.assertEqual(mod.audit(text)['status'],'FAIL')
    def test_embedded_rollback_to_old_rc_is_rejected(self):
        text=(R/'.github/workflows/phase24-official-asm-staging.yml').read_text().replace('rc16','rc15')
        self.assertEqual(mod.audit(text)['status'],'FAIL')
    def test_production_deploy_command_rejected(self):
        text=(R/'.github/workflows/phase24-official-asm-staging.yml').read_text()+'\n      - run: kubectl apply -f deploy.yaml\n'
        self.assertEqual(mod.audit(text)['status'],'FAIL')
if __name__=='__main__':unittest.main()
