"""2020..2051 table and zero-based encoding from HMCLOCK user_custs1_impl.c."""
from datetime import date
YEAR_INFO=(0x7954,0x6aa0,0xad50,0x5b52,0x4b60,0xa6e6,0xa4e0,0xd260,0xea65,0xd530,
0x5aa0,0x76a3,0x96d0,0x4afb,0x4ad0,0xa4d0,0xd0b6,0xd250,0xd520,0xdd45,
0xb5a0,0x56d0,0x55b2,0x49b0,0xa577,0xa4b0,0xaa50,0xb255,0x6d20,0xada0,0x4b63,0x9370)
def lunar_fields(day):
    offset=(day-date(2020,1,25)).days
    if offset<0: raise ValueError('日期早于农历表起点 2020-01-25')
    for y,bits in enumerate(YEAR_INFO):
        for m in range(12):
            days=29+bool(bits&(0x8000>>m))
            if offset<days:return y,m,offset+1
            offset-=days
            if bits&15==m+1:
                days=29+bool(0x48010000&(1<<y))
                if offset<days:return y,m|128,offset+1
                offset-=days
    raise ValueError('日期超出农历表 2051 年')
