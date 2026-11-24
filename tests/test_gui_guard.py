import contextlib,io,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase
from portal.local_gateway import OneCRuntime,LocalERPGUIDisabled,gui_launch_enabled


class GUIGuardTests(SimpleTestCase):
    def test_default_runtime_does_not_write_request_or_start_platform(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'.local/1c/qa-guard';base.mkdir(parents=True);(base/'1Cv8.1CD').touch()
            binary=root/'binary';binary.touch()
            with patch.dict(os.environ,{'ONE_C_ALLOW_GUI':'0'}):
                runtime=OneCRuntime('qa-guard',root,binary)
                with patch('portal.local_gateway.subprocess.run') as launch:
                    with self.assertRaises(LocalERPGUIDisabled):runtime.invoke({'method':'GET','path':'/health','actor':'a'})
                    launch.assert_not_called()
                self.assertFalse((runtime.directory/'request.json').exists())
            self.assertFalse(gui_launch_enabled(False));self.assertTrue(gui_launch_enabled(True))

    def test_cli_setup_and_platform_command_fail_before_launch_without_optin(self):
        import run_local
        from scripts import one_c
        for main,argv in [(run_local.main,['run_local.py','--setup-demo']),
                          (one_c.main,['one_c.py','check'])]:
            with patch.dict(os.environ,{'ONE_C_ALLOW_GUI':'0'}),patch.object(sys,'argv',argv),patch('subprocess.run') as launch,contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):main()
                launch.assert_not_called()

    def test_native_verifiers_require_explicit_manual_optin_before_any_setup(self):
        from scripts import verify_erp,verify_local_install
        for run,args in [(verify_erp.verify,('qa-test',Path('/tmp/not-used.json'))),
                         (verify_local_install.verify,(Path('/tmp/not-used.json'),Path(sys.executable)))]:
            with patch('subprocess.run') as launch:
                with self.assertRaises(SystemExit):run(*args)
                launch.assert_not_called()
