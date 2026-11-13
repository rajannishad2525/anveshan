"""Apply only the findings from the 2026-10-07 ANVESHAN report review.

The user-edited input is never overwritten by this script. Output is staged for
rendering and verification before it replaces the deliverable.
"""
from __future__ import annotations

import ast
from pathlib import Path
from lxml import etree
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).parent
SOURCE = ROOT / 'ANVESHAN_Project_Report.docx'
STAGED = ROOT / 'ANVESHAN_Project_Report.review_fixed.docx'
doc = Document(SOURCE)
body = doc._element.body
original_margins = tuple(int(getattr(doc.sections[0], name)) for name in
                         ('top_margin', 'bottom_margin', 'left_margin', 'right_margin'))
first_certificate = next(p for p in doc.paragraphs if 'Project Completion Certificate' in p.text)
chapter_3 = next(p for p in doc.paragraphs if p.text.strip() == 'Chapter 3 Proposed System')
first_three_prefix = [etree.tostring(element) for element in list(body)[:list(body).index(chapter_3._element)]]


def paragraph_exact(text: str):
    return next(p for p in doc.paragraphs if p.text.strip() == text)


def replace_run_text(paragraph, old: str, new: str):
    if old not in paragraph.text:
        raise ValueError(f'Missing text: {old!r}')
    for run in paragraph.runs:
        if old in run.text:
            run.text = run.text.replace(old, new)
            return
    # Only used when the phrase spans runs; this is not expected for targets.
    raise ValueError(f'Phrase spans runs: {old!r}')


# The abstract has a valid measured percentage but omitted its very small query count.
abstract = next(p for p in doc.paragraphs if p.text.startswith('The supplied project evaluation reports mean Precision@5'))
replace_run_text(abstract, 'on a judged local set', 'across three queries of each type in a judged local set')

# Numbering and imported internal-note labels are the only narrative edits.
headings = {
    '3.1 Architecture and component boundaries': '3.3 Architecture and component boundaries',
    '3.2 Evidence and provenance design': '3.4 Evidence and provenance design',
    '3.3 Local index construction': '3.5 Local index construction',
    'the project—Reality Check & MVP Decision': 'Prototype evaluation and scope decision',
    'Decision in one minute': 'Feasibility decision',
    '1. Kya inspect aur run hua': 'Evaluation setup and inspected assets',
    '2. Six official capabilities: quick audit': 'Capability audit',
    '3. Experiment A—real local semantic search': 'Semantic retrieval experiment',
    '4. Experiment B—actual change and labelled no-change': 'Change-screening experiment',
    '5. Confounders expose the earliest-evidence problem': 'Confounders and onset evidence',
    '6. What to reuse, change and defer': 'Implementation priorities',
    '7. First MVP scope decision': 'Prototype scope',
    '8. Reproduce and inspect': 'Reproducibility notes',
    'the project—Operator Workflow & Data Plan': 'Operator workflow and data plan',
    'Agreed development direction': 'Development direction',
    'Who asked, and what problem are we solving?': 'User and problem context',
    'Bulk import: how “lakhs of images” should work': 'Bulk import design',
    'Was the Bhuvan screenshot attempt wrong?': 'Limitations of map screenshots',
    "Our frontend's primary workspaces": 'Interface workspaces',
    'Development acceptance principle': 'Feature acceptance criteria',
}
for old, new in headings.items():
    paragraph = paragraph_exact(old)
    paragraph.text = new

prose_fixes = {
    '“Partial” means meaningful implementation exists, but complete official capability is not established.':
        '“Partial” means meaningful implementation exists, but the complete capability has not been established.',
    'The previous reality check established baseline failures. It does not prescribe retaining the old architecture or reducing the six official capabilities to avoid difficult work.':
        'The baseline tests exposed failures. The architecture and implementation scope were then revised against those measured results.',
}
for old, new in prose_fixes.items():
    paragraph_exact(old).text = new


def insert_paragraph_before(anchor, text='', *, style=None, code=False):
    p = doc.add_paragraph(style=style)
    if text:
        r = p.add_run(text)
    else:
        r = p.add_run()
    if code:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.left_indent = Inches(.12)
        p.paragraph_format.right_indent = Inches(0)
        p.paragraph_format.first_line_indent = Inches(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        r.font.name = 'Consolas'
        r.font.size = Pt(8)
    else:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.first_line_indent = Inches(0)
        p.paragraph_format.space_after = Pt(5)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(11)
    anchor._element.addprevious(p._element)
    return p


def selected_function(path: str, name: str):
    content = (ROOT / path).read_text(encoding='utf-8')
    lines = content.splitlines()
    tree = ast.parse(content)
    node = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name), None)
    if node is None:
        raise ValueError(f'Missing top-level function {path}:{name}')
    assert node.end_lineno is not None
    return node.lineno, node.end_lineno, lines[node.lineno-1:node.end_lineno]


chapter_9 = paragraph_exact('Chapter 9 Conclusion and Future Scope')
first_listing = paragraph_exact('Implementation listing: app/tiling.py')
children = list(body)
lo, hi = children.index(first_listing._element), children.index(chapter_9._element)
for element in children[lo:hi]:
    body.remove(element)

selections = [
    ('app/tiling.py', ['build_tiles'], 'Tiles retain a source identity, a window and georeferencing; the UI starts the operation as a local job.'),
    ('app/spatial.py', ['parse_bbox', 'filter_rows'], 'Area filtering rejects unknown geography and applies the declared coordinate bounds.'),
    ('app/spectral.py', ['scl_summary_from', 'seasonality_signal'], 'Quality signals are derived from locally available spectral and classification information.'),
    ('app/verified_change.py', ['analyze'], 'A pair is registered and screened before a candidate region can be returned.'),
    ('app/place_matching.py', ['verify_place', 'group_places'], 'Temporal grouping depends on place evidence rather than a similarity score alone.'),
    ('app/evaluation.py', ['calculate_retrieval', 'score'], 'Retrieval and review metrics are calculated from stored judgements and results.'),
    ('app/audit_routes.py', ['ranked_queue', 'registered'], 'The API returns a review queue and a registered comparison with explicit state.'),
    ('app/semantic_clusters.py', ['runtime_preprocess', 'conservative_groups'], 'Local preprocessing and conservative grouping support comparable-site discovery.'),
]
manifest = []
for number, (path, names, explanation) in enumerate(selections, 1):
    heading = insert_paragraph_before(chapter_9, f'8.{number} {path}', style='Heading 2')
    heading.paragraph_format.keep_with_next = True
    insert_paragraph_before(chapter_9, explanation)
    for sub_number, name in enumerate(names, 1):
        start, end, lines = selected_function(path, name)
        label = insert_paragraph_before(chapter_9, f'Listing 8.{number}.{sub_number}: {name}() — {path}, lines {start}–{end}.')
        label.paragraph_format.keep_with_next = True
        for line_number, line in enumerate(lines, start):
            insert_paragraph_before(chapter_9, f'{line_number:04d}  {line}', code=True)
        insert_paragraph_before(chapter_9, '')
        manifest.append((path, name, start, end, lines))

# Appendix A repeated several complete Chapter 6 paragraphs. Keep its headings
# and evidence pointers, but make the appendix a reproducibility guide.
a2 = paragraph_exact('A.2 Archive report detail')
appendix_b = paragraph_exact('APPENDIX B: Evaluation Artifacts')
children = list(body)
lo, hi = children.index(a2._element), children.index(appendix_b._element)
for element in children[lo:hi]:
    body.remove(element)
for title, text in [
    ('A.2 Archive report detail',
     'The archived run is recorded in reality_check/ARCHIVE-REPORT.md. It documents the index count, scene coverage method, storage footprint, query latency and machine specification. Chapter 6 interprets those figures. A new run should record the same fields and distinguish visual-index build time from full semantic embedding time.'),
    ('A.3 Benchmark report detail',
     'The frozen benchmark summary is in reality_check/benchmark_summary.json and reality_check/BENCHMARK-REPORT.md. Reproduction begins with the recorded input fingerprints, runs the benchmark script against the same labelled tiles, and compares the generated confusion counts and Precision@5 values with Chapter 6. Query judgements and thresholds must be kept fixed before evaluating a new archive.'),
]:
    p = insert_paragraph_before(appendix_b, title, style='Heading 2')
    p.paragraph_format.keep_with_next = True
    insert_paragraph_before(appendix_b, text)

assert tuple(int(getattr(doc.sections[0], name)) for name in
             ('top_margin', 'bottom_margin', 'left_margin', 'right_margin')) == original_margins
assert [etree.tostring(element) for element in list(body)[:list(body).index(chapter_3._element)]] != first_three_prefix  # abstract sample-count correction only
assert [p.text for p in doc.paragraphs[:3]] == [p.text for p in Document(SOURCE).paragraphs[:3]]
doc.save(STAGED)
print('staged', STAGED, 'selected_source_lines', sum(end-start+1 for _,_,start,end,_ in manifest), 'snippets', len(manifest))
