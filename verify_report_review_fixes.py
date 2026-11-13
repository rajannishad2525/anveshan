"""Read-only checks before promoting the staged ANVESHAN report."""
import hashlib
import re
from collections import Counter
from pathlib import Path

import pypdfium2 as pdfium
from PIL import ImageChops
from docx import Document
from pypdf import PdfReader

root = Path(__file__).parent
original = Document(root / 'ANVESHAN_Project_Report.before_review_fixes.docx')
updated = Document(root / 'ANVESHAN_Project_Report.review_fixed.docx')
old_pdf = pdfium.PdfDocument(str(root / '_ANVESHAN_review_current.pdf'))
new_pdf = pdfium.PdfDocument(str(root / '_ANVESHAN_review_fixed.pdf'))

assert len(PdfReader(root / '_ANVESHAN_review_fixed.pdf').pages) >= 70
for i in range(3):
    a = old_pdf[i].render(scale=1).to_pil().convert('RGB')
    b = new_pdf[i].render(scale=1).to_pil().convert('RGB')
    assert ImageChops.difference(a,b).getbbox() is None, f'protected page {i+1} changed'

def section(doc, start, end):
    ps=doc.paragraphs
    a=next(i for i,p in enumerate(ps) if p.text.strip()==start)
    b=next(i for i,p in enumerate(ps) if p.text.strip()==end)
    return [(p.style.name,p.text) for p in ps[a:b]]

assert section(original,'Chapter 1 Introduction','Chapter 3 Proposed System') == section(updated,'Chapter 1 Introduction','Chapter 3 Proposed System')
assert [int(getattr(original.sections[0],n)) for n in ('top_margin','bottom_margin','left_margin','right_margin')] == [int(getattr(updated.sections[0],n)) for n in ('top_margin','bottom_margin','left_margin','right_margin')]
assert 'across three queries of each type' in '\n'.join(p.text for p in updated.paragraphs)
for new_heading in ('3.3 Architecture and component boundaries','3.4 Evidence and provenance design','3.5 Local index construction'):
    assert any(p.text==new_heading for p in updated.paragraphs)
for old_heading in ('1. Kya inspect aur run hua','the project—Reality Check & MVP Decision','the project—Operator Workflow & Data Plan'):
    assert not any(p.text==old_heading for p in updated.paragraphs)

module=None
code_count=0
for p in updated.paragraphs:
    if p.style.name=='Heading 2' and re.match(r'^8\.[1-8] app/',p.text):
        module=p.text.split(' ',1)[1]
    elif p.style.name=='Heading 1' and p.text.startswith('Chapter 9'):
        module=None
    match=re.match(r'^([0-9]{4})  (.*)$',p.text)
    if module and match:
        n=int(match.group(1)); expected=(root/module).read_text(encoding='utf-8').splitlines()[n-1]
        assert match.group(2)==expected,(module,n)
        assert len(p.text.splitlines())==1
        assert p.runs and p.runs[0].font.name=='Consolas'
        code_count+=1
assert code_count==686,code_count

counts=Counter(p.text.strip() for p in updated.paragraphs if len(p.text.strip())>80)
duplicates=[text for text,n in counts.items() if n>1 and 'project work' not in text.lower() and 'Dr. Ashwini' not in text and 'work has been carried out' not in text and 'work presented in this report' not in text]
assert not duplicates,duplicates[:3]

def actual_page(title):
    hits=[i+1 for i in range(len(new_pdf)) if title in new_pdf[i].get_textpage().get_text_range()]
    return hits[-1] if hits else None

for title in ('8.1 app/tiling.py','8.8 app/semantic_clusters.py','Chapter 9 Conclusion and Future Scope'):
    entry=next(p.text for p in updated.paragraphs if p.style.name.lower().startswith('toc') and title in p.text)
    stated=int(entry.rsplit('\t',1)[1])
    actual=actual_page(title)
    assert actual==stated,(title,stated,actual)

print('PASS: 70 pages; protected pages/margins; Chapter 1–2; 686 exact code lines; index; no repeated body paragraphs')
