import json, re, sys, logging, statistics
from collections import Counter, defaultdict
from pathlib import Path
logging.disable(logging.INFO)
sys.path.insert(0, str(Path.home()/'mnt/UDA-Bench-main/systems/WDIRS'))
import sqlglot
from sqlglot import exp
from quwarts.core.router.registry import get_corpus, PROJECT, RESULTS
from quwarts.eval.represent_eval import gold_cells
from quwarts.eval import materialize_stream as MS
from quwarts.eval.drift_pool import statements, FOLDER
from quwarts.eval import router_shared_read_run as rs
from quwarts.core.router.corpus_features import read_document
from quwarts.core.adapt import controller as C

corpus = sys.argv[1]
spec, _tr, _te, _run, docs = MS.context(corpus)
qs = {}
for i, s in enumerate(statements(PROJECT/'Query'/FOLDER[corpus]/'Splits'/'train.sql')): qs[f'split#{i}'] = s
train, _ = rs.workload(corpus)
for r in train: qs[r['query_id']] = r['sql']
# usage per attribute
use = defaultdict(Counter)
for q, s in qs.items():
    try: tree = sqlglot.parse_one(s, read='sqlite')
    except Exception: continue
    for node in tree.walk():
        if isinstance(node, exp.Column):
            p = node.parent; kinds=[]
            while p is not None and not isinstance(p, exp.Select):
                t = type(p).__name__
                kinds.append(t); p = p.parent
            k = set(kinds)
            name = node.name
            if 'Group' in k: use[name]['group'] += 1
            if 'Where' in k: use[name]['where'] += 1
            if k & {'Like','ILike'}: use[name]['like'] += 1
            if k & {'EQ','NEQ','In'}: use[name]['eq/in'] += 1
            if k & {'GT','GTE','LT','LTE','Between'}: use[name]['range'] += 1
            if k & {'Add','Sub','Mul','Div'}: use[name]['arith'] += 1
            if 'Case' in k: use[name]['case'] += 1
            if k & {'Avg','Sum','Min','Max'}: use[name]['num-agg'] += 1
            if 'Distinct' in k: use[name]['distinct'] += 1
            if k & {'Substring','StrToTime','TimeToStr','Anonymous','Cast','Lower','Upper','Trim','Length'}: use[name]['func'] += 1
            if 'Is' in k: use[name]['isnull'] += 1
            if 'Join' in k: use[name]['join'] += 1
desc = spec.benchmark_attribute_descriptions(purpose='protocol')
gold = gold_cells(corpus, spec)
out = {}
for t in spec.tables:
    attrs = desc.get(t.attributes_key, {})
    rows = {d: r for (tb, d), r in gold.items() if tb == t.sql_name}
    for a, info in attrs.items():
        if not use.get(a) and not use.get(a.lower()): continue
        vals = []; verb = 0; n = 0; multi = 0; num = 0; ex_miss = []
        for d, r in list(rows.items()):
            g = r.get(a.lower(), r.get(a))
            if g is None or str(g).strip() in ('', 'None', 'nan', 'null', 'NULL'): continue
            gs = str(g).strip(); vals.append(gs); n += 1
            if '||' in gs or re.search(r',\s', gs) and len(gs) < 200: multi += 1
            if re.fullmatch(r'-?[\d.,]+', gs): num += 1
            path = docs[t.sql_name].get(d)
            if path is None: continue
            text = read_document(path).lower()
            parts = [p.strip() for p in re.split(r'\|\|', gs) if p.strip()]
            hit = all(p.lower() in text for p in parts)
            if not hit and re.fullmatch(r'-?[\d.]+', gs):
                v = float(gs); hit = any(x in text for x in {gs, str(int(v)) if v == int(v) else gs, f'{v:,.0f}'})
            verb += hit
            if not hit and len(ex_miss) < 3: ex_miss.append(gs[:40])
        if not n: continue
        c = Counter(vals)
        out[f'{t.sql_name}.{a}'] = {
            'desc': (info.get('description') if isinstance(info, dict) else str(info))[:110] if info else '',
            'type': info.get('value_type', info.get('type')) if isinstance(info, dict) else None,
            'use': dict(use.get(a) or use.get(a.lower())), 'n': n, 'null%': round(1 - n / max(1, len(rows)), 2),
            'distinct': len(c), 'top': [k[:25] for k, _ in c.most_common(4)], 'numeric%': round(num / n, 2),
            'multi%': round(multi / n, 2), 'verbatim%': round(verb / n, 2) if rows else None, 'miss_ex': ex_miss}
print(json.dumps({'corpus': corpus, 'train_queries': len(qs), 'attrs': out}, ensure_ascii=False))
