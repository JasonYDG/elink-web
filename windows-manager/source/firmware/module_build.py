"""Host-only static module inventory; no descriptor table is shipped to the device."""
from pathlib import Path
import hashlib
import json
import re


def load_modules(firmware):
    firmware = Path(firmware).resolve()
    registry = json.loads((firmware / 'modules.json').read_text(encoding='utf-8'))
    if (registry.get('format'), registry.get('api_version'), registry.get('composition')) != (
            'elink-static-modules-1', 1, 'static-unity'):
        raise ValueError('Unsupported static module format')
    if not isinstance(registry.get('modules'), list) or not registry['modules']:
        raise ValueError('Static module inventory must not be empty')
    ids, paths, functions = set(), set(), set()
    for module in registry['modules']:
        name = module['id']
        if not re.fullmatch('[a-z][a-z0-9_]*', name) or name in ids:
            raise ValueError('Invalid or duplicate module ID: ' + name)
        ids.add(name)
        if not module['sources'] or not module['hooks']:
            raise ValueError('Module must declare sources and hooks: ' + name)
        for role, sources in module['sources'].items():
            if role not in ('c_fragment', 'c_source', 'asm_fragment') or not sources:
                raise ValueError('Unsupported or empty source role: ' + role)
            for relative in sources:
                relative.encode('ascii')
                path = (firmware / relative).resolve()
                if (not path.is_relative_to(firmware) or Path(relative).is_absolute()
                        or path in paths or not path.is_file()):
                    raise ValueError('Invalid, missing or duplicate module source: ' + relative)
                paths.add(path)
        for function in module.get('owned_functions', []):
            if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', function) or function in functions:
                raise ValueError('Invalid or duplicate function owner: ' + function)
            functions.add(function)
    return registry


def section_limits(firmware):
    text = (firmware / 'product_ui.ld').read_text(encoding='utf-8')
    return {name: int(limit, 16) for name, limit in re.findall(
        r'ASSERT\(SIZEOF\((\.[a-z_]+)\) <= (0x[0-9a-fA-F]+)', text)}


def expand_assembly(firmware, source, registry):
    fragments = {p for m in registry['modules'] for p in m['sources'].get('asm_fragment', [])}
    for path in fragments:
        directive = '.include "' + path + '"'
        if source.count(directive) != 1:
            raise ValueError('Assembly fragment must be composed exactly once: ' + path)
        source = source.replace(directive, (firmware / path).read_text(encoding='utf-8'))
    if re.search(r'^\s*\.include\b', source, re.M):
        raise ValueError('Unregistered assembly include')
    return source


def module_functions(firmware, registry, symbols, image_labels):
    """Function sizes exclude shared primitives, rodata and linker padding."""
    result = {}
    owned = set()
    for module in registry['modules']:
        name = module['id']
        selected = {s: v for s, v in symbols.items() if any(
            s == f or s.startswith(f + '.') for f in module.get('owned_functions', []))}
        for hook in module['hooks'].values():
            if hook not in symbols and hook not in image_labels:
                raise ValueError('Missing compiled module hook: ' + name + '/' + hook)
        if owned.intersection(selected):
            raise ValueError('Compiled function has multiple owners')
        owned.update(selected)
        result[name] = {
            'hooks': {k: hex(symbols[v]['address'] | 1) if v in symbols else hex(image_labels[v])
                      for k, v in module['hooks'].items()},
            'function_bytes': sum(v['bytes'] for v in selected.values()),
            'functions': selected,
            'source_sha256': {p: hashlib.sha256((firmware / p).read_bytes()).hexdigest()
                              for paths in module['sources'].values() for p in paths},
        }
    result['image']['assembly_span_bytes'] = image_labels['resume'] - image_labels['begin']
    result['shared_core'] = {
        'function_bytes': sum(v['bytes'] for s, v in symbols.items() if s not in owned),
        'functions': {s: v for s, v in symbols.items() if s not in owned},
    }
    return result
