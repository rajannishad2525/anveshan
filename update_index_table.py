from copy import deepcopy
from pathlib import Path
import re

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

path = Path(__file__).parent / 'ANVESHAN_Project_Report.docx'
doc = Document(path)
paras = doc.paragraphs
start = next(i for i, p in enumerate(paras) if p.text == 'INDEX')
end = next(i for i in range(start + 1, len(paras)) if paras[i].text == 'LIST OF ABBREVIATIONS')
entries = []
for p in paras[start + 1:end]:
    if '\t' in p.text:
        label, page = p.text.rsplit('\t', 1)
        if page.strip().isdigit():
            match = re.match(r'^(Chapter\s+\d+|\d+\.\d+|[AB]\.\d+)\s+(.*)$', label.strip())
            entries.append((match.group(1) if match else '', match.group(2) if match else label.strip(), page.strip()))

if not entries:
    old_table = next(t for t in doc.tables if t.cell(0, 0).text == 'Chapter' and t.cell(0, 1).text == 'Title')
    entries = [tuple(c.text for c in row.cells) for row in old_table.rows[1:]]
    old_table._tbl.getparent().remove(old_table._tbl)
assert len(entries) == 52, f'Unexpected index length: {len(entries)}'
anchor = paras[start]._p
table = doc.add_table(rows=1, cols=3)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.autofit = False
for cell, width in zip(table.rows[0].cells, (Inches(.95), Inches(4.8), Inches(.5))):
    cell.width = width
for cell, value in zip(table.rows[0].cells, ('Chapter', 'Title', 'Page')):
    cell.text = value
    shading = OxmlElement('w:shd')
    shading.set(qn('w:fill'), 'E7EDF4')
    cell._tc.get_or_add_tcPr().append(shading)
    for run in cell.paragraphs[0].runs:
        run.bold = True
for chapter, title, page in entries:
    row = table.add_row()
    for cell, value in zip(row.cells, (chapter, title, page)):
        cell.text = value
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
for row in table.rows:
    for cell in row.cells:
        for p in cell.paragraphs:
            p.style = doc.styles['Normal']
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1
            if cell == row.cells[2]:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.font.name = 'Times New Roman'
                run.font.size = Pt(7.5)
    for cell, width in zip(row.cells, (Inches(.95), Inches(4.8), Inches(.5))):
        cell.width = width

tbl_pr = table._tbl.tblPr
borders = OxmlElement('w:tblBorders')
for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
    border = OxmlElement(f'w:{side}')
    border.set(qn('w:val'), 'single')
    border.set(qn('w:sz'), '3')
    border.set(qn('w:color'), 'BFC8D2')
    borders.append(border)
tbl_pr.append(borders)
anchor.addnext(table._tbl)

for p in paras[start + 1:end]:
    if p.text or p._p.xpath('.//w:fldChar'):
        p._p.getparent().remove(p._p)

doc.save(path)
print(f'Updated {path} with {len(entries)} index rows')
