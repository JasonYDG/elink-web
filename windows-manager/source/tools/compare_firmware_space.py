"""Compare two built images and their bounded regions without touching hardware."""
import argparse
import hashlib
import json
from pathlib import Path


def read_build(directory):
    meta = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    images = {}
    for kind, size_key in (('app', 'app_bytes'), ('spi', 'bytes')):
        raw = (directory / f'elink-bwr-{meta["version"]}-{kind}.bin').read_bytes()
        if len(raw) != meta[size_key] or hashlib.sha256(raw).hexdigest() != meta[kind + '_sha256']:
            raise ValueError('Build image does not match its manifest: ' + str(directory))
        images[kind] = raw
    return meta, images


def compare(baseline, current):
    before, old_images = read_build(baseline)
    after, new_images = read_build(current)
    space = json.loads((current / 'space-report.json').read_text(encoding='utf-8'))
    if space['app_sha256'] != after['app_sha256'] or space['spi_sha256'] != after['spi_sha256']:
        raise ValueError('Space report belongs to a different build')
    if set(before['product_regions']) != set(after['product_regions']):
        raise ValueError('Region sets changed; compare their layouts explicitly')
    regions = {}
    for name, region in after['product_regions'].items():
        old = before['product_regions'][name]
        if old['address'] != region['address']:
            raise ValueError('Region relocated: ' + name)
        regions[name] = {'before': old['bytes'], 'after': region['bytes'],
                         'delta': region['bytes'] - old['bytes'],
                         'limit': space['regions'][name]['limit'],
                         'free': space['regions'][name]['free']}
    return {'format': 'elink-module-comparison-1', 'baseline': str(baseline.resolve()),
            'current': str(current.resolve()),
            'images_identical': {k: old_images[k] == new_images[k] for k in old_images},
            'firmware_id_before': before['firmware_id'], 'firmware_id_after': after['firmware_id'],
            'app_bytes_before': before['app_bytes'], 'app_bytes_after': after['app_bytes'],
            'app_bytes_delta': after['app_bytes'] - before['app_bytes'],
            'regions': regions,
            'extension_bytes_delta': after['code_bytes'] - before['code_bytes'],
            'runtime_bytes_delta': after['runtime_bytes'] - before['runtime_bytes'],
            'hardware_access': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--current', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-identical', action='store_true')
    args = parser.parse_args()
    result = compare(args.baseline, args.current)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    if args.require_identical and not all(result['images_identical'].values()):
        raise SystemExit('Firmware bytes changed; inspect the comparison before proceeding')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
