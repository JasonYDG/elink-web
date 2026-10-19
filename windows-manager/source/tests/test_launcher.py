"""Exercise the real CMD launcher failure paths without opening device data."""
import os,subprocess,tempfile,time,unittest,socket
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
LAUNCHER=ROOT/'source/tools/Start.cmd'

@unittest.skipUnless(os.name=='nt','Windows CMD is required')
class Launcher(unittest.TestCase):
    def failure(self,localappdata,expected,script='Start.cmd',args=()):
        with tempfile.TemporaryDirectory(prefix='elink-launch-') as tmp:
            directory=Path(tmp)/'partial delivery';directory.mkdir()
            (directory/script).write_bytes((ROOT/'source/tools'/script).read_bytes())
            if script=='Stop.cmd':
                (directory/'tools').mkdir();(directory/'tools/Stop-Manager.ps1').write_bytes((ROOT/'source/tools/Stop-Manager.ps1').read_bytes())
            env={**os.environ,'LOCALAPPDATA':str(localappdata or Path(tmp)/'profile')}
            output=Path(tmp)/'console.txt'
            with output.open('wb') as console:
                p=subprocess.Popen([os.environ['ComSpec'],'/d','/c','call',str(directory/script),*args],cwd=tmp,env=env,stdin=subprocess.PIPE,stdout=console,stderr=subprocess.STDOUT)
                try:
                    end=time.monotonic()+20
                    while b'Press any key' not in output.read_bytes():
                        self.assertIsNone(p.poll(),'Failed startup closed before acknowledgement')
                        if time.monotonic()>end:self.fail('Expected retained error message')
                        time.sleep(.05)
                    self.assertIsNone(p.poll());p.communicate(b'\r\n',timeout=5)
                    self.assertEqual(p.returncode,expected)
                finally:
                    if p.poll() is None:p.terminate();p.wait(timeout=5)
            return output.read_bytes()

    def test_ascii_launcher_and_missing_executable_keep_error_visible(self):
        raw=LAUNCHER.read_bytes();self.assertTrue(raw.isascii());self.assertNotIn(b'\xef\xbb\xbf',raw)
        self.assertIn(b'Extract the complete ZIP',self.failure(None,2))

    def test_ascii_stop_wrapper_reports_absent_service_and_keeps_result_visible(self):
        for name in ('Stop.cmd','Stop-Manager.ps1'):self.assertTrue((ROOT/'source/tools'/name).read_bytes().isascii())
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.assertIn(b'is not running',self.failure(None,0,'Stop.cmd',('-Port',str(port))))

if __name__=='__main__':unittest.main()
