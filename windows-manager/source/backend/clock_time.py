"""Computer-local or Netherlands wall time using the bundled IANA TZif."""
import datetime,hashlib,json,sys
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

ZONES=('local','Europe/Amsterdam')

@lru_cache(maxsize=1)
def dutch_zone():
    folder=(Path(sys._MEIPASS)/'source' if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])/'timezones'
    meta=json.loads((folder/'provenance.json').read_text('utf-8'))
    raw=(folder/meta['file']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=meta['file_sha256']:raise ValueError('荷兰时区数据哈希不一致')
    with (folder/meta['file']).open('rb') as file:return ZoneInfo.from_file(file,key='Europe/Amsterdam')

def wall_time(zone='local',now=None):
    if zone not in ZONES:raise ValueError('时区仅支持本地或荷兰 Europe/Amsterdam')
    now=now or datetime.datetime.now().astimezone()
    return now if zone=='local' else now.astimezone(dutch_zone())

def timezone_packet(zone='local',now=None):
    t=wall_time(zone,now)
    return bytes([0x9f,int(zone!='local'),int(zone!='local' and bool(t.dst()))])

def settings(config=None):
    result={'mode':0,'full_every':10,'refresh_minutes':5,'advertise_minutes':1,'window_seconds':0,'clock_timezone':'local'}
    result.update(config or {})
    if result['clock_timezone'] not in ZONES:raise ValueError('不支持此时区')
    return result
