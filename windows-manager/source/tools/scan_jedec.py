import glob

files = glob.glob(r'C:/Program Files (x86)/SmartSnippetsToolbox/SmartSnippetsToolbox5.0.10/common_resources/SupportPackages/*/toolbox_resources/common/*.bin')

def variants(pat):
    return {
        'plain': pat,
        'u16swap': pat[1::-1] + pat[3:1:-1],
        'rev': pat[::-1],
    }

for f in files:
    data = open(f, 'rb').read()
    hits = []
    for name, hexs in {'WinbondEF': 'EF4013', 'MXIC': 'C22013', 'GD': 'C84013',
                       'Micron': '204013', 'Fudan': 'A14013'}.items():
        for vn, v in variants(bytes.fromhex(hexs)).items():
            if v in data:
                hits.append(f'{name}/{vn}@{hex(data.find(v))}')
    parts = f.replace('\\', '/').split('/')
    short = parts[-2] + '/' + parts[-1]
    print(f'{short:55s} => {hits if hits else "no hits"}')
