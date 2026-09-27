"""Read-only checks of local Markdown destinations, fragments and duplicate anchors."""
from pathlib import Path
import re, json, sys, unicodedata
from urllib.parse import unquote
ROOT=Path(__file__).resolve().parents[2]
def slug(s):
 s=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',s).replace('`','').lower()
 return ''.join(c for c in s if c.isalnum() or c in '_- ').replace(' ','-')
def anchors(text):
 explicit=re.findall(r'<a\s+(?:id|name)="([^"]+)"',text)
 result=set(explicit);counts={};fence=False
 for line in text.splitlines():
  if line.startswith('```'):fence=not fence
  if fence:continue
  m=re.match(r'^#{1,6}\s+(.+?)\s*#*$',line)
  if m:
   a=slug(m[1]);n=counts.get(a,0);counts[a]=n+1;result.add(a+(f'-{n}' if n else ''))
 return result,[a for a in set(explicit) if explicit.count(a)>1]
def links(text):
 # Supports angle-bracket destinations and spaces/parentheses in those paths.
 pattern=r'\[[^\]\n]*\]\((?:<([^>]+)>|([^\s)]+))(?:\s+"[^"]*")?\)'
 fence=False
 for n,line in enumerate(text.splitlines(),1):
  if line.startswith('```'):fence=not fence
  if fence:continue
  for m in re.finditer(pattern,line):yield n,m[1] or m[2]
def check(files):
 errors=[];count=0
 for p in files:
  text=p.read_text();_,duplicates=anchors(text)
  for a in duplicates:errors.append(f'{p.relative_to(ROOT)}: duplicate #{a}')
  for line,url in links(text):
   if re.match(r'[a-zA-Z][\w+.-]*:',url):continue
   path,_,frag=unquote(url).partition('#');target=(p.parent/path).resolve() if path else p
   count+=1
   if not target.exists():errors.append(f'{p.relative_to(ROOT)}:{line}: missing {url}')
   elif frag and target.suffix=='.md' and frag not in anchors(target.read_text())[0]:errors.append(f'{p.relative_to(ROOT)}:{line}: fragment {url}')
 return count,errors
if __name__=='__main__':
 manifest=json.loads((ROOT/'docs/文書整理_対象.json').read_text())
 files=[ROOT/p for p in manifest['current_files']]
 count,errors=check(files)
 matrix=(ROOT/'docs/対応表.md').read_text()
 expected=[f'{prefix}{n:02}' for prefix,end in [('P',4),('F',25),('N',2),('T',4),('U',4)] for n in range(1,end+1)]
 ids=re.findall(r'<a id="([pfntu]\d{2})"></a>',matrix)
 for id in expected:
  if ids.count(id.lower())!=1:errors.append(f'ID coverage: {id}')
 acceptance=[f'r-topic-{n:02}' for n in range(21,47)]+['sec-5-2','sec-5-4']
 for a in acceptance:
  if f'受入条件_現行.md#{a}' not in matrix:errors.append(f'Acceptance coverage: {a}')
 if '--all' in sys.argv:
  files=list(ROOT.glob('*.md'))+[p for p in (ROOT/'docs').rglob('*.md') if 'history' not in p.relative_to(ROOT).parts]
  count,all_errors=check(files);errors+=all_errors
 print(json.dumps({'documents':len(files),'local_links':count,'traceability_ids':len(expected),'acceptance_sections':len(acceptance),'errors':errors},ensure_ascii=False,indent=2))
 sys.exit(bool(errors))
