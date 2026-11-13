from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.dml import MSO_THEME_COLOR

OUT = 'False_Alarms_Satellite_Change_Analysis_ANVESHAN.pptx'
W, H = 13.333, 7.5
BG = RGBColor(7, 18, 16)
PANEL = RGBColor(14, 35, 29)
PANEL2 = RGBColor(18, 47, 38)
LIME = RGBColor(183, 227, 93)
MINT = RGBColor(198, 218, 203)
MUTED = RGBColor(139, 169, 153)
AMBER = RGBColor(255, 190, 90)
RED = RGBColor(241, 117, 103)
WHITE = RGBColor(239, 245, 239)

prs = Presentation()
prs.slide_width = Inches(W)
prs.slide_height = Inches(H)

def rect(slide, x, y, w, h, fill=PANEL, line=None, radius=False):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                                   Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid(); shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = line or fill
    return shape

def textbox(slide, text, x, y, w, h, size=18, color=WHITE, bold=False,
            align=PP_ALIGN.LEFT, font='Aptos', margin=0.08):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame; tf.clear(); tf.word_wrap = True
    tf.margin_left = Inches(margin); tf.margin_right = Inches(margin)
    tf.margin_top = Inches(margin); tf.margin_bottom = Inches(margin)
    p = tf.paragraphs[0]; p.alignment = align
    run = p.add_run(); run.text = text
    run.font.name = font; run.font.size = Pt(size); run.font.bold = bold; run.font.color.rgb = color
    return box

def bullets(slide, items, x, y, w, h, size=17, color=MINT, gap=3):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame; tf.clear(); tf.word_wrap = True
    tf.margin_left = Inches(.12); tf.margin_right = Inches(.08)
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = '• ' + item; p.level = 0; p.space_after = Pt(gap)
        p.font.name = 'Aptos'; p.font.size = Pt(size); p.font.color.rgb = color
    return box

def base(title, kicker, number):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.background.fill; bg.solid(); bg.fore_color.rgb = BG
    textbox(slide, 'ANVESHAN', .55, .27, 3.2, .25, 10, MUTED, True)
    textbox(slide, f'{number:02d}', 12.05, .27, .7, .25, 10, LIME, True, PP_ALIGN.RIGHT)
    textbox(slide, kicker.upper(), .6, .82, 5.8, .25, 10, LIME, True)
    textbox(slide, title, .58, 1.08, 12.0, .55, 28, WHITE, True)
    rect(slide, .6, 1.78, 12.1, .015, LIME)
    return slide

def card(slide, x, y, w, h, title, body, accent=LIME, icon=None):
    rect(slide, x, y, w, h, PANEL, PANEL2, True)
    rect(slide, x, y, .06, h, accent, accent)
    textbox(slide, (icon + '  ' if icon else '') + title, x+.22, y+.17, w-.4, .38, 16, accent, True)
    textbox(slide, body, x+.22, y+.65, w-.4, h-.8, 12.5, MINT)

# 1
s=base('False Alarms in Satellite Change Analysis', 'Concept briefing', 1)
textbox(s, 'When imagery looks different, the ground has not always changed.', .62, 2.25, 8.8, .7, 24, MINT)
rect(s, .65, 3.35, 5.55, 2.35, PANEL, PANEL2, True)
textbox(s, 'A FALSE ALARM', .95, 3.68, 4.9, .35, 14, AMBER, True)
textbox(s, 'The system reports “change”\nwhen there is no meaningful change on the ground.', .95, 4.22, 4.6, .95, 22, WHITE, True)
rect(s, 7.0, 3.22, 4.85, 2.6, PANEL2, PANEL2, True)
textbox(s, 'Operational goal', 7.35, 3.58, 4.1, .35, 15, LIME, True)
textbox(s, 'Fewer alerts\n+ more useful and reliable alerts', 7.35, 4.1, 4.0, 1.15, 25, WHITE, True)

# 2
s=base('Why a visual difference can be misleading', 'The problem', 2)
textbox(s, 'A change detector sees pixels first. An analyst must ask what caused the pixels to change.', .62, 2.12, 11.6, .45, 17, MINT)
card(s,.65,2.85,3.8,2.65,'Seasonal variation','Brown field in summer → green field after rain.\n\nDifferent appearance, same land use.',LIME,'01')
card(s,4.78,2.85,3.8,2.65,'Cloud / haze / snow','The ground is partly hidden or colours are suppressed.\n\nVisibility is different; the asset may be unchanged.',AMBER,'02')
card(s,8.91,2.85,3.8,2.65,'Misregistration','The same building is shifted by a few pixels.\n\nEdges appear everywhere even when nothing moved.',RED,'03')
textbox(s, 'The key question is not “Did pixels change?”  It is “Is the change meaningful and observable?”', .8, 6.05, 11.7, .5, 18, LIME, True, PP_ALIGN.CENTER)

# 3
s=base('The eight main “confusers”', 'Confusers', 3)
items=[('Cloud','ground hidden','SCL / S2 Cloudless'),('Haze','contrast reduced','atmospheric correction'),('Snow','objects masked white','NDSI'),('Shadow','dark false change','FMask / KappaMask'),('Season','normal land variation','BFAST / EWMACD'),('Sun angle','brightness shift','radiometric normalization'),('Misregistration','pixels displaced','co-registration / AROSICS'),('Illumination','same object looks different','normalization')]
for i,(a,b,c) in enumerate(items):
    x=.65+(i%4)*3.1; y=2.25+(i//4)*1.85
    rect(s,x,y,2.75,1.38,PANEL,PANEL2,True)
    textbox(s,a,x+.16,y+.13,2.4,.27,14,LIME,True)
    textbox(s,b,x+.16,y+.52,2.4,.27,12,WHITE,True)
    textbox(s,c,x+.16,y+.92,2.4,.3,10,MUTED)
textbox(s,'These are causes of uncertainty—not proof of an actual change.',.8,6.25,11.7,.35,17,AMBER,True,PP_ALIGN.CENTER)

# 4
s=base('Three examples an officer can explain', 'Examples', 4)
card(s,.65,2.25,3.8,3.25,'Field: brown → green','Observed difference: colour and texture.\nLikely confuser: season.\nDecision cue: compare multiple dates and avoid calling it construction without structural evidence.',LIME,'A')
card(s,4.78,2.25,3.8,3.25,'Building edge halo','Observed difference: outline around the whole building.\nLikely confuser: misregistration.\nDecision cue: align images before measuring change.',AMBER,'B')
card(s,8.91,2.25,3.8,3.25,'Cloud-covered scene','Observed difference: bright/low-detail patch.\nLikely confuser: cloud or haze.\nDecision cue: mark low-observation area; do not infer what is underneath.',RED,'C')
textbox(s,'A defensible alert includes the suspected cause and its evidence quality.',.8,6.15,11.7,.4,18,LIME,True,PP_ALIGN.CENTER)

# 5
s=base('A false-alarm-aware comparison workflow', 'Mitigation logic', 5)
steps=[('01','Screen','Cloud, haze, snow, shadow and low-quality pixels'),('02','Align','Check source grid and co-register before pixel comparison'),('03','Normalize','Reduce illumination and radiometric differences'),('04','Compare','Measure only the common, usable overlap'),('05','Explain','Return change cue + caveat + reason for rejection')]
for i,(n,t,b) in enumerate(steps):
    x=.62+i*2.5
    rect(s,x,3.0,2.15,2.2,PANEL,PANEL2,True)
    textbox(s,n,x+.2,3.28,1.6,.3,14,LIME,True)
    textbox(s,t,x+.2,3.78,1.75,.38,18,WHITE,True)
    textbox(s,b,x+.2,4.35,1.72,.6,11,MINT)
    if i<4: textbox(s,'→',x+2.18,3.75,.3,.4,24,AMBER,True,PP_ALIGN.CENTER)
textbox(s,'The sequence reduces misleading alerts before they reach a human decision queue.',.75,6.15,11.8,.4,17,LIME,True,PP_ALIGN.CENTER)

# 6
s=base('What each mitigation is trying to protect', 'Methods', 6)
rows=[('Cloud / snow masking','Do not compare pixels that are not observing the ground.'),('Haze / illumination normalization','Make brightness differences less likely to look structural.'),('Co-registration','Put the same ground feature in the same pixel position.'),('Season-aware temporal reasoning','Treat expected environmental variation as context, not automatic change.'),('Usable-overlap mask','Measure change only where both observations are valid.')]
for i,(a,b) in enumerate(rows):
    y=2.22+i*.78;rect(s,.75,y,11.8,.58,PANEL,PANEL2,True)
    textbox(s,a,.98,y+.12,3.1,.3,14,LIME,True)
    textbox(s,b,4.35,y+.12,7.7,.3,13,MINT)
textbox(s,'Tools such as SCL / S2 Cloudless, NDSI, FMask, BFAST, EWMACD and AROSICS are examples of methods—not automatic guarantees.',.82,6.4,11.7,.45,12,AMBER,False,PP_ALIGN.CENTER)

# 7
s=base('Explain the rejection, not only the alert', 'Analyst-facing output', 7)
rect(s,.7,2.3,5.15,3.55,PANEL,PANEL2,True)
textbox(s,'Suspected change',1.05,2.68,4.4,.35,16,WHITE,True)
textbox(s,'“18% of usable overlap differs”',1.05,3.28,4.2,.45,23,LIME,True)
textbox(s,'Evidence cue\n• registered pair\n• common valid area\n• candidate regions',1.05,4.1,4.3,1.2,15,MINT)
rect(s,6.55,2.3,5.9,3.55,PANEL2,PANEL2,True)
textbox(s,'Possible rejection reason',6.95,2.68,5.0,.35,16,AMBER,True)
textbox(s,'“No reliable change conclusion”',6.95,3.28,4.9,.45,23,WHITE,True)
textbox(s,'Reason\n• cloud / haze obscures ground\n• seasonal variation likely\n• source grids not aligned',6.95,4.1,4.8,1.2,15,MINT)
textbox(s,'Transparency turns a false alarm into a reviewable decision.',.8,6.25,11.7,.35,18,LIME,True,PP_ALIGN.CENTER)

# 8
s=base('Takeaway: reliability beats alert volume', 'Closing message', 8)
textbox(s,'A strong satellite change-analysis system should:', .75,2.18,7.0,.38,20,WHITE,True)
bullets(s,['separate real change from image-condition change','show the likely confuser when evidence is weak','withhold a conclusion when the scene is not reliably observable','keep the analyst in the decision loop'],.9,2.85,7.0,2.3,18,MINT,6)
rect(s,8.35,2.28,4.05,3.18,PANEL2,PANEL2,True)
textbox(s,'LESS\nNOISE',8.75,2.72,3.2,.8,28,AMBER,True,PP_ALIGN.CENTER)
textbox(s,'MORE\nACTIONABLE\nEVIDENCE',8.75,3.75,3.2,1.15,25,LIME,True,PP_ALIGN.CENTER)
textbox(s,'False-alarm reduction is not about hiding alerts.\nIt is about making every alert easier to trust.',.9,6.15,11.6,.55,18,WHITE,True,PP_ALIGN.CENTER)

prs.core_properties.title = 'False Alarms in Satellite Change Analysis'
prs.core_properties.subject = 'Concept briefing for ANVESHAN'
prs.core_properties.author = 'ANVESHAN'
prs.save(OUT)
print(OUT)
