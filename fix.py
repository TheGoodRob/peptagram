import peptagram.proteins

import json

fname = 'examples/comparison/data.js'
with open(fname) as f:
  txt = f.read().replace('var data = ', '')

data = json.loads(txt)
proteins = data['proteins']
print proteins.keys()

bad_seqids = 'F8VQJ3 E9QN70 P02469 P10493 P19137 F8VQ40'.split()

for seqid in bad_seqids:
  if seqid in proteins:
    del proteins[seqid]

peptagram.proteins.save_data_js(data, fname)

