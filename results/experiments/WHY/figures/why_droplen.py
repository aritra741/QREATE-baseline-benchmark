"""Drop rate of DocETL (Qwen, realistic players run) by document length, field sets without championship."""
import json, glob, collections, sys
S = sys.argv[1]
tok = json.load(open(S + '/edge/player/doc_tokens.json'))
D = collections.defaultdict(collections.Counter)
for st in glob.glob('results/docetl_realistic_ollama/player/*/table_*/stats.json'):
    s = json.load(open(st)); t = s['table']
    if len(s['fields']) < 2 or 'championship' in s['fields']:
        continue
    failed = {x.rsplit('.', 1)[0] for x in s['failed']}
    for k, L in tok.items():
        if not k.startswith(t + '/'):
            continue
        b = min(int(L // 2000) * 2, 24)
        D[b]['n'] += 1; D[b]['drop'] += k.split('/', 1)[1] in failed
out = {b: [c['n'], c['drop']] for b, c in sorted(D.items())}
print(out)
json.dump(out, open(S + '/whydeck/charts/droplen.json', 'w'))
