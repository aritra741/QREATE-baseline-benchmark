import json, sys
d = json.loads(open(sys.argv[1]).read().strip().splitlines()[-1])
print(d['corpus'], 'train queries', d['train_queries'])
for k, v in d['attrs'].items():
    print(f"{k} [{v['type']}] use={v['use']} n={v['n']} null={v['null%']} dist={v['distinct']} num={v['numeric%']} multi={v['multi%']} verb={v['verbatim%']} top={v['top']} miss={v['miss_ex']} | {v['desc'][:90]}")
