"""OS-held single-writer lock released automatically if the process crashes."""
import os
class DataLock:
    def __init__(self,path):
        self.file=open(path,'a+b')
        if self.file.tell()==0:self.file.write(b'1');self.file.flush()
        self.file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise RuntimeError('该数据目录已有后台运行，请使用已打开的控制台。') from exc
    def close(self):self.file.close()
