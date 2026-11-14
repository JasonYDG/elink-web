"""Independent bit order, padding, untouched output pixels and release provenance."""
from pathlib import Path
import hashlib,json,os,struct,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'source/tools'))
from preview_firmware import frame_image,export_frame,verify_firmware,FIRMWARE_DIR


class NativePreview(unittest.TestCase):
    def test_every_visible_bit_and_padding_map_to_exactly_one_pixel(self):
        raw=bytes((i*73+19)%256 for i in range(8000));im=frame_image(raw)
        self.assertEqual(im.size,(250,122))
        for y in range(122):
            for x in range(250):
                offset=(249-x)*16+y//8;bit=128>>(y%8)
                expected=(190,0,0) if raw[4000+offset]&bit else (255,255,255) if raw[offset]&bit else (0,0,0)
                self.assertEqual(im.getpixel((x,y)),expected,(x,y))
        altered=bytearray(raw)
        for plane in (0,4000):
            for gate in range(250):altered[plane+gate*16+15]^=63
        self.assertEqual(frame_image(altered).tobytes(),im.tobytes())

    def test_corners_and_byte_boundaries_do_not_wrap_or_mirror(self):
        raw=bytearray(b'\xff'*4000+bytes(4000));points=((0,0),(249,0),(0,121),(249,121),(17,7),(18,8))
        for x,y in points:raw[(249-x)*16+y//8]&=255^(128>>(y%8))
        im=frame_image(raw)
        self.assertEqual(sum(c for c,color in im.getcolors() if color==(0,0,0)),len(points))
        for point in points:self.assertEqual(im.getpixel(point),(0,0,0))
        with self.assertRaises(ValueError):frame_image(bytes(7999))

    def test_png_export_never_resizes_or_draws_fonts(self):
        raw=b'\xaa'*4000+b'\x22'*4000
        with tempfile.TemporaryDirectory() as path,patch('PIL.Image.Image.resize',side_effect=AssertionError('Resampling forbidden')),patch('PIL.ImageDraw.Draw',side_effect=AssertionError('Drawing forbidden')),patch('PIL.ImageFont.truetype',side_effect=AssertionError('Font rendering forbidden')):
            report=export_frame(path,'native',raw);file=Path(path)/'native.png'
            self.assertEqual(struct.unpack('>II',file.read_bytes()[16:24]),(250,122))
            self.assertEqual((Path(path)/'native.bwr.bin').read_bytes(),raw)
            with Image.open(file) as saved:self.assertEqual(saved.tobytes(),frame_image(raw).tobytes())
            self.assertEqual(report['frame_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(report['scale'],1)

    def test_different_application_or_identity_is_rejected(self):
        meta=json.loads((FIRMWARE_DIR/'manifest.json').read_text('utf-8'))
        package=FIRMWARE_DIR/f'elink-bwr-{meta["version"]}.elink-update.json'
        self.assertEqual(verify_firmware(FIRMWARE_DIR,package)['application_sha256'],meta['app_sha256'])
        with tempfile.TemporaryDirectory() as path:
            target=Path(path);name=f'elink-bwr-{meta["version"]}-app.bin';raw=(FIRMWARE_DIR/name).read_bytes()
            (target/'manifest.json').write_text(json.dumps(meta),encoding='utf-8')
            (target/name).write_bytes(bytes([raw[0]^1])+raw[1:])
            with self.assertRaises(ValueError):verify_firmware(target,package)
            (target/name).write_bytes(raw);meta['firmware_id']='00000000'
            (target/'manifest.json').write_text(json.dumps(meta),encoding='utf-8')
            with self.assertRaises(ValueError):verify_firmware(target,package)

    def test_generator_refuses_implicit_old_build_selection(self):
        env={k:v for k,v in os.environ.items() if k not in ('ELINK_TEST_FIRMWARE_DIR','ELINK_PREVIEW_UPDATE_PACKAGE')}
        for name in ('preview_screen_design.py','preview_firmware.py'):
            result=subprocess.run([sys.executable,'-B',str(ROOT/'source/tools'/name)],env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('no legacy build fallback',result.stderr)


if __name__=='__main__':unittest.main()
