from pathlib import Path
import json,datetime
root=Path(__file__).resolve().parents[1]/'opendesign'
sections=[]
for section,label in [('mockups','Mockups'),('design-systems','Design Systems')]:
    groups=[]
    for folder in sorted((root/section).iterdir()):
        if not folder.is_dir():continue
        files=[{'label':str(p.relative_to(folder)),'path':p.relative_to(root).as_posix()} for p in sorted(folder.rglob('*')) if p.is_file() and (section!='mockups' or p.suffix=='.html')]
        if files:groups.append({'slug':folder.name,'files':files})
    sections.append({'id':section,'label':label,'groups':groups})
(root/'manifest.json').write_text(json.dumps({'generated':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sections':sections},indent=2),encoding='utf-8')
