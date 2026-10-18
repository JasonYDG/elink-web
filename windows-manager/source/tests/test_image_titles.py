import unittest,tempfile,sqlite3,json,sys
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from normalize_image_titles import normalize

class ImageTitles(unittest.TestCase):
    def test_explicit_translation_keeps_every_other_column_and_custom_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'elink.sqlite3'
            with closing(sqlite3.connect(path)) as db,db:
                db.executescript('CREATE TABLE templates(id,title,spec,frame);CREATE TABLE jobs(status);')
                db.executemany('INSERT INTO templates VALUES(?,?,?,?)',[(1,'Window-Cat','{"kind":"image"}',b'pixels-a'),(2,'My cat','{"kind":"image"}',b'pixels-b'),(3,'Cat','{"kind":"notice"}',b'pixels-c')])
            dry=normalize(path);self.assertFalse(dry['applied']);self.assertEqual(len(dry['changes']),1)
            result=normalize(path,True);self.assertTrue(Path(result['backup']).is_file())
            with closing(sqlite3.connect(path)) as db:self.assertEqual(db.execute('SELECT * FROM templates ORDER BY id').fetchall(),[(1,'窗边小猫','{"kind":"image"}',b'pixels-a'),(2,'My cat','{"kind":"image"}',b'pixels-b'),(3,'Cat','{"kind":"notice"}',b'pixels-c')])
            self.assertFalse(normalize(path,True)['applied'])
    def test_pending_device_operation_prevents_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'elink.sqlite3'
            with closing(sqlite3.connect(path)) as db,db:
                db.executescript('CREATE TABLE templates(id,title,spec);CREATE TABLE jobs(status);INSERT INTO templates VALUES(1,\'Cat\',\'{"kind":"image"}\');INSERT INTO jobs VALUES(\'waiting\');')
            with self.assertRaisesRegex(ValueError,'任务尚未结束'):normalize(path,True)
            with closing(sqlite3.connect(path)) as db:self.assertEqual(db.execute('SELECT title FROM templates').fetchone()[0],'Cat')
