"""Generate honest UI previews by executing the built binary with model SPI/GPIO."""
import os,sys,struct
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'source/tests'),str(ROOT/'source/backend')]
from test_product_ui import ProductMachine,BASE,STATE,FIRMWARE_DIR

def frame_image(frame):
    if len(frame)!=8000:raise ValueError('BWR frame must be 8000 bytes')
    im=Image.new('RGB',(250,122),'white')
    for x in range(250):
        for y in range(122):
            pos=(249-x)*16+y//8;mask=128>>(y&7)
            if frame[4000+pos]&mask:im.putpixel((x,y),(190,0,0))
            elif not frame[pos]&mask:im.putpixel((x,y),(0,0,0))
    return im

if __name__=='__main__':
    m=ProductMachine();m.uc.mem_write(BASE+0x104dc+0x18,struct.pack('<H',1647))
    m.uc.mem_write(BASE+0xdd98+0x20,bytes(4)) # No season calculation in direct RTC fixture.
    frame_image(m.draw(force=128)).save(FIRMWARE_DIR/'clock-preview.png');m.finish()
    m.uc.mem_write(STATE+7,b'\x03')
    frame_image(m.draw(force=128)).save(FIRMWARE_DIR/'calendar-preview.png')
