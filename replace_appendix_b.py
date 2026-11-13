"""Replace raw debug JSON in Appendix B with concise academic result tables."""
from pathlib import Path
from lxml import etree
from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

path=Path('ANVESHAN_Project_Report.docx')
d=Document(path)
body=d._element.body
ch3=next(p for p in d.paragraphs if p.text.strip()=='Chapter 3 Proposed System')
boundary=list(body).index(ch3._element)
prefix=[etree.tostring(x) for x in list(body)[:boundary]]
margins=tuple(int(getattr(d.sections[0],n)) for n in ('top_margin','bottom_margin','left_margin','right_margin'))
appendix=next(p for p in d.paragraphs if p.text.strip()=='APPENDIX B: Evaluation Artifacts')
after=False
for child in list(body):
    if child is appendix._element:
        after=True
        continue
    if after and child.tag!=qn('w:sectPr'):
        body.remove(child)

def prose(s):
    p=d.add_paragraph(s)
    p.paragraph_format.space_after=Pt(6)
    p.paragraph_format.line_spacing=1.13
    for run in p.runs:
        run.font.name='Times New Roman'; run.font.size=Pt(12)

def result_table(title,headers,rows):
    p=d.add_heading(title,2)
    p.paragraph_format.space_before=Pt(10)
    t=d.add_table(rows=1,cols=len(headers))
    t.style='Table Grid'
    for i,h in enumerate(headers): t.rows[0].cells[i].text=h
    for row in rows:
        cells=t.add_row().cells
        for i,value in enumerate(row): cells[i].text=str(value)
    for row in t.rows:
        for cell in row.cells:
            for pp in cell.paragraphs:
                pp.paragraph_format.space_after=Pt(2)
                for r in pp.runs:
                    r.font.name='Times New Roman'; r.font.size=Pt(9)
    d.add_paragraph()

prose('This appendix summarises the machine-readable project artifacts in a form suitable for review. The corresponding JSON files in the project folder retain the detailed run records. The figures below should be interpreted with the sample definitions and limitations stated in Chapter 6.')
result_table('B.1 Change-screening operating point',['Measure','Before gate','After gate'],[
    ('Labelled OSCD tiles','169','169'),('Positive tiles','31','31'),('Negative tiles','138','138'),
    ('False positives','116','74'),('True positives','28','25'),('Precision','19.4%','25.3%'),('Recall','90.3%','80.6%')])
prose('The gate removes 42 false positives and three true positives in this sample. It therefore reduces review burden while losing some relevant examples. The threshold was selected for the experiment; it is not a calibrated probability or a universal acceptance rule.')
result_table('B.2 Retrieval and workflow checks',['Check','Recorded result','Scope'],[
    ('Text-query mean Precision@5','26.7%','Judged local retrieval queries'),
    ('Image-query mean Precision@5','53.3%','Judged local retrieval queries'),
    ('RemoteCLIP average precision','0.198','Change-screening baseline'),
    ('Pixel baseline average precision','0.150','Same screening comparison'),
    ('Timeline observations checked','4','Workflow smoke test'),
    ('Incremental old vectors','Unchanged','Synthetic georeferenced fixture'),
    ('Raster pixel round-trip','Passed','Synthetic georeferenced fixture')])
prose('The ingestion fixture checks that adding two synthetic georeferenced tiles can preserve earlier vectors and round-trip pixel data. It does not establish accuracy on new satellite imagery or crash recovery. Retrieval labels were provisional judgements by one reviewer. A geographically and temporally independent evaluation remains necessary.')
result_table('B.3 Evidence interpretation',['Artifact','What it supports','What it does not support'],[
    ('benchmark_summary.json','Reproducible tile-level screening counts','Operational change-type accuracy'),
    ('retrieval_eval_final.json','Judged local ranking results','General retrieval performance'),
    ('workflow_results.json','Selected local workflow behaviour','Full archive-scale deployment'),
    ('threshold_operating_point.json','Documented threshold experiment','Calibrated confidence')])

assert [etree.tostring(x) for x in list(body)[:boundary]]==prefix
assert tuple(int(getattr(d.sections[0],n)) for n in ('top_margin','bottom_margin','left_margin','right_margin'))==margins
d.save(path)
print('Appendix B replaced; protected elements',boundary)
