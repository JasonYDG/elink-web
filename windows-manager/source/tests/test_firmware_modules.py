"""Static module registration and budgets against the actual compiled firmware."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from test_firmware import ROOT, FIRMWARE_DIR

sys.path.insert(0, str(ROOT / 'source/firmware'))
from module_build import load_modules, expand_assembly, section_limits


class FirmwareModules(unittest.TestCase):
    def test_compiled_inventory_hooks_hashes_and_region_accounting(self):
        firmware = ROOT / 'source/firmware'
        inventory = load_modules(firmware)
        report = json.loads((FIRMWARE_DIR / 'space-report.json').read_text())
        meta = json.loads((FIRMWARE_DIR / 'manifest.json').read_text())
        symbols = json.loads((FIRMWARE_DIR / 'product-functions.json').read_text())
        self.assertEqual([m['id'] for m in inventory['modules']], meta['static_modules']['ids'])
        self.assertEqual(meta['static_modules']['runtime_descriptor_bytes'], 0)
        self.assertEqual(report['app_sha256'], meta['app_sha256'])
        self.assertEqual(report['spi_sha256'], meta['spi_sha256'])
        for name, limit in section_limits(firmware).items():
            region = report['regions'][name]
            self.assertEqual(region['used'], meta['product_regions'][name]['bytes'])
            self.assertEqual(region['used'] + region['free'], limit)
            self.assertGreaterEqual(region['free'], 0)
        owned = []
        for module in inventory['modules']:
            actual = report['modules'][module['id']]
            owned.extend(actual['functions'])
            self.assertEqual(actual['function_bytes'], sum(v['bytes'] for v in actual['functions'].values()))
            self.assertEqual(set(actual['hooks']), set(module['hooks']))
            for source, digest in actual['source_sha256'].items():
                self.assertEqual(hashlib.sha256((firmware / source).read_bytes()).hexdigest(), digest)
            for role, symbol in module['hooks'].items():
                if module['id'] != 'image':
                    self.assertEqual(int(actual['hooks'][role], 16), symbols[symbol]['address'] | 1)
        owned.extend(report['modules']['shared_core']['functions'])
        self.assertEqual(len(owned), len(set(owned)))
        self.assertEqual(set(owned), set(symbols))
        self.assertLessEqual(sum(v['bytes'] for v in symbols.values()), sum(r['used'] for r in report['regions'].values()))
        image = report['modules']['image']
        start = int(image['hooks']['begin'], 16) & ~1
        self.assertGreater(image['assembly_span_bytes'], 0)
        self.assertLessEqual(start + image['assembly_span_bytes'], int(meta['state_address'], 16))
        self.assertEqual(report['extension']['used'], meta['code_bytes'])
        self.assertEqual(report['runtime']['used'], meta['runtime_bytes'])

    def test_invalid_inventory_is_rejected_before_compilation(self):
        with tempfile.TemporaryDirectory() as directory:
            firmware = Path(directory) / 'firmware'
            shutil.copytree(ROOT / 'source/firmware', firmware, ignore=shutil.ignore_patterns('__pycache__'))
            path = firmware / 'modules.json'
            original = path.read_text()
            def reject(change):
                data = json.loads(original)
                change(data)
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    load_modules(firmware)
            reject(lambda d: d.update(api_version=2))
            reject(lambda d: d.update(modules=[]))
            reject(lambda d: d['modules'].append(d['modules'][0]))
            reject(lambda d: d['modules'][0]['sources'].update(c_fragment=['../outside.c']))
            reject(lambda d: d['modules'][0]['sources'].update(c_fragment=['missing.inc']))
            reject(lambda d: d['modules'][1]['sources'].update(c_fragment=['modules/clock/render.inc']))

    def test_image_fragment_must_be_registered_and_composed_once(self):
        firmware = ROOT / 'source/firmware'
        registry = load_modules(firmware)
        source = (firmware / 'extension.s').read_text()
        directive = '.include "modules/image/commands.s"'
        expanded = expand_assembly(firmware, source, registry)
        self.assertNotIn('.include ', expanded)
        for text in (source.replace(directive, ''), source + '\n' + directive,
                     source + '\n.include "unregistered.s"'):
            with self.assertRaises(ValueError):
                expand_assembly(firmware, text, registry)
