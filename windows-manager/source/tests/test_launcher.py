"""Exercise the real CMD launcher failure paths without opening device data."""
import os,subprocess,tempfile,time,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
LAUNCHER=ROOT/'source/tools/Start.cmd'

@unittest.skipUnless(os.name=='nt','Windows CMD is required')
class Launcher(unittest.TestCase):
    def failure(self,localappdata,expected):
        with tempfile.TemporaryDirectory(prefix='elink-launch-') as tmp:
            directory=Path(tmp)/'partial delivery';directory.mkdir()
            (directory/'Start.cmd').write_bytes(LAUNCHER.read_bytes())
            env={**os.environ,'LOCALAPPDATA':str(localappdata or Path(tmp)/'profile')}
            output=Path(tmp)/'console.txt'
            with output.open('wb') as console:
                p=subprocess.Popen([os.environ['ComSpec'],'/d','/c','call',str(directory/'Start.cmd')],cwd=tmp,env=env,stdin=subprocess.PIPE,stdout=console,stderr=subprocess.STDOUT)
                try:
                    end=time.monotonic()+8
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

if __name__=='__main__':unittest.main()
