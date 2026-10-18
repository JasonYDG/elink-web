"""Explicit, backed-up translation of existing imported image labels; pixels/IDs stay intact."""
from pathlib import Path
import argparse,datetime,json,sqlite3
from contextlib import closing

TITLES={'Mountain':'山水风景','Sleep-Cat':'安睡小猫','Netherlands':'荷兰风景','Meeeting':'会议安排','Cat':'小猫','Window-Cat':'窗边小猫'}

def normalize(path,apply=False):
    path=Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        changes=[{'id':ident,'old':title,'new':TITLES[title]} for ident,title,spec in db.execute('SELECT id,title,spec FROM templates') if title in TITLES and json.loads(spec).get('kind')=='image']
        if not apply or not changes:return {'changes':changes,'applied':False}
        stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');backup=path.parent/'backups'/('image-titles-'+stamp+'.sqlite3');backup.parent.mkdir(exist_ok=True)
        with closing(sqlite3.connect(backup)) as target:db.backup(target)
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','waiting','running','awaiting_display')").fetchone()[0]:raise ValueError('屏幕任务尚未结束，名称未修改')
        for item in changes:
            if db.execute('UPDATE templates SET title=? WHERE id=? AND title=?',(item['new'],item['id'],item['old'])).rowcount!=1:raise ValueError('图片列表已变化，名称未修改')
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    return {'changes':changes,'applied':True,'backup':str(backup)}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',required=True,type=Path);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    print(json.dumps(normalize(args.data/'elink.sqlite3',args.apply),ensure_ascii=False,indent=2))
