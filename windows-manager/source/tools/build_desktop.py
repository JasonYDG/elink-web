"""Build from exact source/UI paths into build/desktop; never flashes a device."""
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
if not str(Path(sys.executable).resolve()).lower().startswith(str(ROOT/'runtime/venv').lower()):
    raise SystemExit('Use runtime/venv/Scripts/python.exe')
cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--name','ElinkManager','--console',
     '--distpath',str(ROOT/'build/desktop'),'--workpath',str(ROOT/'build/pyinstaller'),'--specpath',str(ROOT/'build'),
     '--add-data',str(ROOT/'source/opendesign/mockups/elink-manager')+';source/opendesign/mockups/elink-manager',
     '--add-data',str(ROOT/'source/opendesign/design-systems/elink-home/tokens/colors_and_type.css')+';source/opendesign/design-systems/elink-home/tokens',
     '--add-data',str(ROOT/'source/fonts')+';source/fonts',
     '--add-data',str(ROOT/'source/timezones')+';source/timezones',
     '--add-data',str(ROOT/'source/web/config.json')+';source/web',
     '--add-data',str(ROOT/'source/web/image')+';source/web/image',
     '--collect-submodules','winrt']
# Conda-backed venvs keep these native dependencies outside DLLs and PATH.
for name in ('sqlite3.dll','ffi.dll'):
    library=Path(sys.base_prefix)/'Library/bin'/name
    if library.is_file():cmd+=['--add-binary',str(library)+';.']
cmd.append(str(ROOT/'source/backend/server.py'))
subprocess.run(cmd,cwd=ROOT,check=True)
