import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('reconcile_local_env',Path(__file__).resolve().parents[1]/'reconcile_local_env.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReconciliationTests(unittest.TestCase):
    def test_preserves_existing_bytes_empty_values_and_comments_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            template=Path(directory)/'example';target=Path(directory)/'env'
            template.write_text('A=default\nEMPTY=default\n# Audit cap\nAUDIT_TRAIL_SEARCH_RESULT_LIMIT=1000\n')
            original=b'# Private configuration\nexport A=private\nEMPTY='
            target.write_bytes(original);target.chmod(0o600)
            added,skipped=module.reconcile(template,target)
            self.assertEqual(added,['AUDIT_TRAIL_SEARCH_RESULT_LIMIT']);self.assertEqual(skipped,[])
            self.assertTrue(target.read_bytes().startswith(original+b'\n'))
            self.assertIn('# Audit cap\nAUDIT_TRAIL_SEARCH_RESULT_LIMIT=1000',target.read_text())
            result=target.read_bytes()
            self.assertEqual(module.reconcile(template,target),([],[]))
            self.assertEqual(target.read_bytes(),result)
            self.assertEqual(target.stat().st_mode & 0o777,0o600)

    def test_new_file_is_private_and_example_credentials_are_not_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            template=Path(directory)/'example';target=Path(directory)/'env'
            template.write_text('DATABASE_URL=postgresql://erms:replace-with-a-password@host/db\nWEBUI_STORAGE_SECRET=local-development-change-me\nLIMIT=1000\n')
            added,skipped=module.reconcile(template,target)
            self.assertEqual(skipped,['DATABASE_URL'])
            self.assertEqual(added,['WEBUI_STORAGE_SECRET','LIMIT'])
            text=target.read_text()
            self.assertNotIn('DATABASE_URL=',text);self.assertNotIn('local-development-change-me',text)
            self.assertEqual(target.stat().st_mode & 0o777,0o600)

    def test_launcher_reconciles_after_lock_and_before_loading(self):
        script=(Path(__file__).resolve().parents[2]/'run-local-stack.sh').read_text()
        self.assertLess(script.index('unset ERMS_LOCAL_STACK_LOCK_PID'),script.index('tools/reconcile_local_env.py'))
        self.assertLess(script.index('tools/reconcile_local_env.py'),script.index('source "${PROJECT_ENV_FILE}"'))


if __name__=='__main__':unittest.main()
