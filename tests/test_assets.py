import pathlib
import struct
import unittest

PROJECT = pathlib.Path(__file__).resolve().parents[1]

class AssetsTests(unittest.TestCase):
    def test_icon_is_multisize_and_png_valid(self):
        ico=(PROJECT/'assets'/'SMSGateDesk.ico').read_bytes()
        png=(PROJECT/'assets'/'SMSGateDesk.png').read_bytes()
        reserved, kind, count = struct.unpack_from('<HHH', ico, 0)
        self.assertEqual((reserved, kind),(0,1))
        dimensions=set()
        for i in range(count):
            width,height=struct.unpack_from('<BB', ico, 6+16*i)
            dimensions.add((width or 256, height or 256))
        for size in (16,32,48,256):
            self.assertIn((size,size),dimensions)
        self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(struct.unpack('>II', png[16:24]), (1024,1024))

    def test_builder_embeds_resource(self):
        script=(PROJECT/'BUILD_WINDOWS.bat').read_text(encoding='utf-8')
        self.assertIn('--icon "assets\\SMSGateDesk.ico"',script)
        self.assertIn('--add-data "assets\\SMSGateDesk.ico;assets"',script)
        self.assertIn('python tests\\gui_smoke.py',script)
        self.assertIn('--credential-self-test',script)

if __name__=='__main__': unittest.main()
