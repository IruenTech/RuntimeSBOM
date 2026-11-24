"""Test negative conditions without misrepresenting a fake JAR as official ASM."""
import importlib.util
import struct
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('phase22_audit',ROOT/'scripts/phase22-binary-audit.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class BinaryAuditNegativeTest(unittest.TestCase):
    def test_missing_agent_rejected(self):
        with tempfile.TemporaryDirectory() as p:
            result=audit.audit(Path(p)/'nonexistent.jar')
            self.assertEqual(result['status'],'FAIL')
            self.assertFalse(result['checks']['artifactAvailable'])

    def test_java17_class_in_root_rejected(self):
        with tempfile.TemporaryDirectory() as p:
            jar=Path(p)/'fake.jar'
            with ZipFile(jar,'w') as z:
                z.writestr('com/iruen/runtimesbom/Injected.class',b'\xca\xfe\xba\xbe'+struct.pack('>HH',0,61)+b'junk')
            result=audit.audit(jar)
            self.assertFalse(result['checks']['everyRootClassJava8Compatible'])
            self.assertEqual(result['incompatibleClasses'][0]['major'],61)

    def test_duplicate_zip_entries_rejected(self):
        with tempfile.TemporaryDirectory() as p:
            jar=Path(p)/'duplicate.jar'
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning)
                with ZipFile(jar,'w') as z:
                    z.writestr('com/iruen/runtimesbom/Agent.class',b'first')
                    z.writestr('com/iruen/runtimesbom/Agent.class',b'second')
            result=audit.audit(jar)
            self.assertFalse(result['checks']['noDuplicateZipEntries'])

if __name__=='__main__':unittest.main()
