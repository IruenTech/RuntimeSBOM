import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('gate23',ROOT/'scripts/phase23-staging-gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
spec2=importlib.util.spec_from_file_location('quality23',ROOT/'scripts/phase23-sbom-quality.py')
q=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(q)

class GateTests(unittest.TestCase):
 def test_missing_files_hold(self):
  with tempfile.TemporaryDirectory() as t:
   r=gate.evaluate({'stagingReview':'ELIGIBLE_FOR_HUMAN_REVIEW'},Path(t),Path(t),q)
   self.assertEqual(r['stagingReview'],'HOLD')
   self.assertEqual(len(r['blockingReasons']),8)
 def test_unapproved_base_still_hold(self):
  with tempfile.TemporaryDirectory() as t:
   r=gate.evaluate({'stagingReview':'HOLD'},Path(t),Path(t),q)
   self.assertEqual(r['stagingReview'],'HOLD')
   self.assertEqual(r['productionDeployment'],'HOLD')
if __name__=='__main__':unittest.main()
