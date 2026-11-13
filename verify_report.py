from pypdf import PdfReader
from docx import Document
from zipfile import ZipFile

r=PdfReader('ANVESHAN_Project_Report.pdf')
print('pages',len(r.pages))
for i,page in enumerate(r.pages):
    t=page.extract_text() or ''
    n=len(t.strip())
    if i<9 or n<350:
        print(i+1,n,repr(t[:110].replace('\n',' ')))
d=Document('ANVESHAN_Project_Report.docx')
print('margins',[round(getattr(d.sections[0],a).inches,3) for a in ['top_margin','bottom_margin','left_margin','right_margin']])
print('certs',sum('Project Completion Certificate' in x.text for x in d.paragraphs))
print('declarations',sum(x.text.strip()=='Declaration' for x in d.paragraphs))
print('toc_paras',sum('toc' in x.style.name.lower() for x in d.paragraphs))
print('images',len([n for n in ZipFile('ANVESHAN_Project_Report.docx').namelist() if n.startswith('word/media/')]))
