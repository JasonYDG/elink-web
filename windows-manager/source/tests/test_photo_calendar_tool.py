import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('photo_device_tool', ROOT / 'source/tools/test_photo_calendar_device.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class PhotoCalendarTool(unittest.TestCase):
    def test_diagnostic_shape_and_capacity_are_not_inferred_from_ff(self):
        value = tool.decode_diagnostic(b'EFD1\x01\x80\x12\xa1' + b'\xff' * 8)
        self.assertEqual(value['legacy_90h_id'], '0xa112')
        self.assertFalse(value['capacity_independently_verified'])
        for raw in (b'', bytes(16), b'EFD1\x02\x80' + bytes(10), b'EFD1\x01\x80' + bytes(11)):
            with self.assertRaises(ValueError):
                tool.decode_diagnostic(raw)

    def test_photo_frame_has_exact_left_width_and_white_date_column(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'black.png'
            Image.new('RGB', (400, 300), 'black').save(path)
            frame = tool.photo_frame(path)
        self.assertEqual(len(frame), 8000)
        for x in range(250):
            for y in range(122):
                pos = (249 - x) * 16 + y // 8
                self.assertEqual(bool(frame[pos] & (128 >> (y & 7))), x >= 174)
        self.assertEqual(frame[4000:], bytes(4000))


if __name__ == '__main__':
    unittest.main()
