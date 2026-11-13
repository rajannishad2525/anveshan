"""Generate paper tables/PR figure directly from frozen result JSON/CSV.

Only completed experiments appear. No manuscript numbers are handwritten here.
"""
import csv,json
from pathlib import Path
import numpy as np
from sklearn.metrics import precision_recall_curve
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/oscd_full_v2'
T=ROOT/'tables';F=ROOT/'figures';T.mkdir(exist_ok=True);F.mkdir(exist_ok=True)
summary=json.loads((BASE/'summary.json').read_text(encoding='utf-8'))
pairs=json.loads((BASE/'test_pair_summary.json').read_text(encoding='utf-8'))
random=json.loads((BASE/'random_baseline.json').read_text(encoding='utf-8'))
ci=json.loads((BASE/'bootstrap_ci.json').read_text(encoding='utf-8'))
retrieval=json.loads((ROOT/'results/retrieval_chance.json').read_text(encoding='utf-8'))
rows=[r for r in csv.DictReader((BASE/'raw_tile_scores.csv').open(newline='',encoding='utf-8')) if r['split']=='test']
y=np.array([int(r['truth']) for r in rows])
assert len(y)==summary['test_tiles'] and int(y.sum())==summary['test_positives']

def table(name,caption,label,header,lines):
    cols=len(header)
    body='\\begin{table}[t]\n\\caption{'+caption+'}\n\\label{'+label+'}\n\\centering\n'
    body+='\\begin{tabular}{'+'l'+'r'*(cols-1)+'}\n\\hline\n'
    body+=' & '.join(header)+r' \\'+'\n\\hline\n'
    body+=''.join(' & '.join(map(str,row))+r' \\'+'\n' for row in lines)
    body+='\\hline\n\\end{tabular}\n\\end{table}\n'
    (T/name).write_text(body,encoding='utf-8')

def pct(v):return f'{100*v:.1f}\\%'
method_names=[('pixel','Pixel difference'),('remoteclip','RemoteCLIP distance'),('gated_remoteclip','RemoteCLIP + gate')]
aggregate=[('All-positive / prevalence',f"{summary['test_prevalence']:.3f}",pct(summary['test_prevalence']),'100.0\\%','0')]
aggregate.append(('Seeded random ranking',f"{random['simulated_random_ap_mean']:.3f}",'--','--','--'))
for key,label in method_names:
    m=summary['methods'][key]
    tp=m['tn_fp_fn_tp'][3];fp=m['tn_fp_fn_tp'][1]
    aggregate.append((label,f"{m['ap']:.3f}",pct(m['precision']),pct(m['recall']),f'{tp}/{fp}'))
table('oscd_aggregate.tex',f"Full OSCD test-pair change screening ({summary['n_test_pairs']} pairs, {summary['test_tiles']} tiles; thresholds from {summary['n_train_pairs']} train pairs).",'tab:oscd',
      ['Method','AP','Prec.','Recall','TP/FP'],aggregate)
table('oscd_pairs.tex','Pair-level OSCD test distribution and ranking AP.','tab:pairs',
      ['Pair','Tiles','Pos.','Remote AP','Pixel AP'],
      [(p['pair'].replace('_',r'\_'),p['tiles'],p['positives'],
        '--' if p['remoteclip_ap'] is None else f"{p['remoteclip_ap']:.3f}",
        '--' if p['pixel_ap'] is None else f"{p['pixel_ap']:.3f}") for p in pairs])
table('retrieval_probe.tex','Provisional Noida relevance probe; expected chance from concept prevalence in the 56-chip pool.','tab:retrieval',
      ['Mode','Queries','Chance P@5','Observed P@5'],
      [('Text',3,pct(retrieval['text_mean_random_expected_p_at_5']),pct(retrieval['text_mean_observed_p_at_5'])),
       ('Image example',3,pct(retrieval['image_mean_random_expected_p_at_5']),pct(retrieval['image_mean_observed_p_at_5']))])

for key,label in method_names:
    score=np.array([float(r['remoteclip']) if key=='gated_remoteclip' else float(r[key]) for r in rows])
    if key=='gated_remoteclip':
        rules=summary['gate_rule_thresholds_preexisting']
        passed=np.ones(len(rows),dtype=bool)
        for name,limit in rules.items():passed &= np.array([float(r['rule_'+name]) for r in rows])<limit
        score=np.where(passed,score,-1.0)
    precision,recall,_=precision_recall_curve(y,score)
    plt.plot(recall,precision,label=label)
plt.axhline(summary['test_prevalence'],color='gray',linestyle='--',label='Prevalence reference')
plt.xlabel('Recall');plt.ylabel('Precision');plt.xlim(0,1);plt.ylim(0,1);plt.legend(fontsize=7);plt.tight_layout()
plt.savefig(F/'oscd_pr_curve.pdf');plt.close()
reg=json.loads((ROOT/'results/registration/summary.json').read_text(encoding='utf-8'))
pert=json.loads((ROOT/'results/perturbation/summary.json').read_text(encoding='utf-8'))
table('registration.tex','Synthetic same-date geometric recovery on 14 training images per transform.','tab:registration',
      ['Transform','Accepted','Median corner RMSE'],
      [(r['case'].replace('_',' '),f"{r['success']}/{r['n']}",f"{r['median_corner_rmse_px_success_only']:.3f} px") for r in reg['rows']])
table('perturbation.tex','Synthetic nuisance flags on 50 training-image chips per case.','tab:perturbation',
      ['Condition','Flagged','Rate'],
      [(r['perturbation'].replace('_',' '),f"{r['flagged']}/{r['n']}",pct(r['flagged_rate'])) for r in pert['cases']])
gate=[('All-positive / prevalence',pct(summary['test_prevalence']),'100.0\\%','--')]
gate.extend((name.replace('_',' '),pct(m['precision']),pct(m['recall']),f"{m['tn_fp_fn_tp'][3]}/{m['tn_fp_fn_tp'][1]}")
            for name,m in summary['methods'].items() if name.startswith('gate_') or name=='gated_remoteclip')
table('gate_ablation.tex','Exploratory fixed-rule ablation; each score cutoff selected on 14 training pairs.','tab:gate',
      ['Variant','Prec.','Recall','TP/FP'],gate)
plt.bar([r['perturbation'].replace('_','\n') for r in pert['cases']],
        [r['flagged_rate'] for r in pert['cases']],color='#305a7d')
plt.ylabel('Flagged fraction');plt.ylim(0,1);plt.tight_layout()
plt.savefig(F/'perturbation_flags.pdf');plt.close()
plt.bar([r['case'].replace('_','\n') for r in reg['rows']],
        [r['median_corner_rmse_px_success_only'] for r in reg['rows']],color='#567d30')
plt.ylabel('Median corner RMSE (pixels)');plt.tight_layout()
plt.savefig(F/'registration_error.pdf');plt.close()
fig,ax=plt.subplots(figsize=(8.2,2.0));ax.set_xlim(0,10);ax.set_ylim(0,2);ax.axis('off')
labels=[('Local imagery\n+ metadata',.9),('Screen &\nembed',2.8),('Index &\nretrieve',4.7),('Register &\nscreen',6.6),('Review &\nexport',8.5)]
for label,x in labels:
    ax.text(x,1,label,ha='center',va='center',fontsize=9,
            bbox={'boxstyle':'round,pad=.4','fc':'#eaf0f7','ec':'#305a7d'})
for a,b in zip(labels,labels[1:]):
    ax.annotate('',xy=(b[1]-.7,1),xytext=(a[1]+.7,1),arrowprops={'arrowstyle':'->','lw':1.2})
fig.tight_layout();fig.savefig(F/'architecture.pdf');fig.savefig(F/'architecture.png',dpi=180);plt.close(fig)
print('Generated 6 tables and 4 figures from frozen JSON/CSV and stated architecture')
