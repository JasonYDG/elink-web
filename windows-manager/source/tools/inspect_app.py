from pathlib import Path
import struct, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
p=Path(__file__).resolve().parents[1]/'reference/hmclock-bwr-baseline-app.bin'
b=p.read_bytes(); c=Cs(CS_ARCH_ARM, CS_MODE_THUMB)
for pair in sys.argv[1:]:
    a,z=[int(x,16) for x in pair.split(':')]
    print('RANGE',hex(a),hex(z))
    for i in c.disasm(b[a:z],0x07fc0000+a):
        print(hex(i.address-0x07fc0000), i.bytes.hex(), i.mnemonic,i.op_str)
        if i.mnemonic=='ldr' and '[pc,' in i.op_str:
            v=(i.address+4)&~3
            off=int(i.op_str.split('#')[1].split(']')[0],0)
            print(' literal',hex(v+off),hex(struct.unpack_from('<I',b,v+off-0x07fc0000)[0]))
