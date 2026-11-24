import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from io import BytesIO

P=Path(__file__).resolve().parents[1]/'scripts/phase20-static-inventory.py'
spec=importlib.util.spec_from_file_location('p20inventory',P)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class StaticInventoryTest(unittest.TestCase):
    def test_jar_from_build_metadata(self):
        with TemporaryDirectory() as d:
            app=Path(d)/'app.jar'
            inner=BytesIO()
            with ZipFile(inner,'w') as j:
                j.writestr('META-INF/maven/com.example/tool/pom.properties','groupId=com.example\nartifactId=tool\nversion=1.2.3')
            with ZipFile(app,'w') as z:
                z.writestr('BOOT-INF/lib/tool.jar',inner.getvalue())
                z.writestr('BOOT-INF/classes/App.class',b'not-a-jar')
            rows=mod.inventory(app)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['purl'],'pkg:maven/com.example/tool@1.2.3')
            sbom={'bomFormat':'CycloneDX','components':[]}
            report=mod.compare(rows,sbom)
            self.assertEqual(report['statusCounts']['PACKAGED_NOT_OBSERVED'],1)
            self.assertNotIn('falseNegatives',report)
            sbom['components']=[{'purl':rows[0]['purl'],'hashes':[{'alg':'SHA-256','content':rows[0]['sha256']}],
                 'properties':[{'name':'runtimeSbom:source','value':'file:'+str(app)+'!/BOOT-INF/lib/tool.jar!/'},
                               {'name':'runtimeSbom:runtimeEvidenceState','value':'CLASS_LOADED'}]}]
            report=mod.compare(rows,sbom)
            self.assertEqual(report['statusCounts']['OBSERVED_EXACT_IDENTITY'],1)
    def test_mismatched_hash_reported(self):
        rows=[{'sourceSuffix':'sample.war!/WEB-INF/lib/x.jar!','purl':'p','sha256':'a'}]
        sbom={'bomFormat':'CycloneDX','components':[{'purl':'p','hashes':[{'alg':'SHA-256','content':'b'}],
              'properties':[{'name':'runtimeSbom:source','value':'file:/a/sample.war!/WEB-INF/lib/x.jar!/' }]}]}
        self.assertEqual(mod.compare(rows,sbom)['statusCounts']['OBSERVED_IDENTITY_MISMATCH'],1)

if __name__=='__main__':unittest.main()
