"""Host-verified HMCLOCK inactive-bank OTA. Only ELK1 update packages accepted."""
import base64,hashlib,json,struct,zlib
BOARD='da14585-5pad-bwr-250x122'
def validate_package(package):
    if not isinstance(package,dict) or package.get('board')!=BOARD or package.get('format')!='elink-update-1':
        raise ValueError('请选择此标签专用的 .elink-update.json 升级包')
    raw=base64.b64decode(package['application'],validate=True)
    state_offset=0xe2d4
    if not state_offset+32<=len(raw)<=65472 or raw[state_offset:state_offset+5]!=b'ELK1\x01' or struct.unpack_from('<I',raw,4)[0]!=0x07fc0111:raise ValueError('升级包不是修复启动布局的 ELK1 应用镜像；旧版 1.0.0 和完整 SPI 镜像不能用于 OTA')
    if hashlib.sha256(raw).hexdigest()!=package.get('sha256'):raise ValueError('升级包 SHA256 不一致')
    if raw[state_offset+28:state_offset+32].hex()!=package.get('firmware_id'):raise ValueError('固件标识不一致')
    magic=bytes.fromhex('79 13 a5 f9 86 ec 5a 06');pos=raw.find(magic)
    if pos<0:raise ValueError('缺少 HMCLOCK 版本标记')
    version=0xa50f0000+struct.unpack_from('<H',raw,pos+8)[0]
    return raw,version
def image(raw,version):
    header=bytearray(b'\xff'*64)
    struct.pack_into('<III',header,0,0x00aa5170,len(raw),zlib.crc32(raw))
    struct.pack_into('<I',header,28,version);header[32]=0
    result=bytes(header)+raw
    return result+b'\xff'*((-len(result))%256)
def page_packets(page):
    if len(page)!=256:raise ValueError('OTA page must be 256 bytes')
    return b'\xa2'+b'\xff'*7+page[:128],b'\xa3'+b'\xff'*7+page[128:]
