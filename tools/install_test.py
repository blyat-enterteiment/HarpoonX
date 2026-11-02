import importlib.util,pathlib,json
root=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('configure',root/'deploy/configure.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
n=0
for books in [['equity'],['crypto'],['equity','crypto']]:
 for gpt in [False,True]:
  c=m.compose(books,gpt,'example.com');s=c['services'];assert ('gpt' in s)==gpt
  for b in books:
   assert 'ports' not in s[b] and s[b]['environment']['HARPOON_START_PAPER']=='1'
   assert s[b]['restart']=='unless-stopped' and s[b]['read_only']
   assert not any('LIVE_AUTHORIZATION' in k for k in s[b]['environment'])
  assert s['https']['ports']==['80:80','443:443'];n+=1
report={'checks':n,'passed':n,'scope':'Six generated configurations; Docker schema/build not executed'}
(root/'evidence/install_tests.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
