import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('p28',ROOT/'scripts/phase28-performance.py')
p28=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(p28)

class Phase28ValidationTests(unittest.TestCase):
    def test_mode_grouping_and_pct(self):
        rows=[]
        for mode,tps,p95,p99 in [('baseline',1000,4,8),('loaded-only',950,4.2,9),('asm-traced',900,5,10)]:
            for n in (1,2):
                rows.append({'mode':mode,'run':n,'successTps':tps,'p95Ms':p95,'p99Ms':p99,'errors':0})
        summary,impact=p28.summarize(rows)
        self.assertEqual(impact['asmTpsChangePercent'],-10)
        self.assertEqual(impact['asmP95ChangePercent'],25)
        self.assertEqual(summary['asm-traced']['repeats'],2)
        self.assertEqual(summary['baseline']['totalHttpErrors'],0)

    def test_cpu_rss_missing_proc_is_nullable(self):
        self.assertIsNone(p28.process_cpu_seconds(-1))
        self.assertIsNone(p28.process_rss_kib(-1))

    def test_official_jar_identity(self):
        import hashlib
        self.assertEqual(hashlib.sha256(p28.JAR.read_bytes()).hexdigest(),p28.EXPECTED_SHA256)

    def test_repeated_modes_use_exact_modes(self):
        self.assertEqual(set(p28.MODES),{'baseline','loaded-only','asm-traced'})

if __name__=='__main__':unittest.main()
