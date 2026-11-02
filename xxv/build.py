from pathlib import Path
import re,hashlib,base64
r=Path(__file__).resolve().parents[1]
h=(r/'HARPOON_XXIV.html').read_text()
for original,current in [('xxv/crypto_engine24.original.js','src/crypto_engine.js'),('xxv/supervision24.original.js','src/supervision.js'),('src/xx_crypto.original25_2.js','src/xx_crypto.js'),('src/crypto_exits.original25_2.js','src/plugins/crypto_exits.js'),('src/plugin_registry.original25_2.js','src/plugin_registry.js'),('src/xx_app.original25_2.js','src/xx_app.js'),('src/ux_app.original25_2.js','src/ux_app.js')]:
 old=(r/original).read_text().strip();assert h.count(old)==1,original
 h=h.replace(old,(r/current).read_text().strip(),1)
addon='\n'.join((r/p).read_text() for p in ['src/profit25.js','src/vector25.js','src/agents25.js','src/agent_adapter25.js','src/agent_research25.js','src/desk25.js','src/warroom3.js','src/warroom_store3.js','src/optimizer3.js','src/optimizer_store3.js','src/warroom_adapter3.js','src/options3.js','src/options_adapter3.js','src/autonomy3.js','src/autonomy_adapter3.js','xxv/ui.js','xxv/warroom_ui3.js','xxv/autonomy_ui3.js'])
h=h.replace('</body></html>','<script>\n'+addon+'\n</script></body></html>')
h=h.replace('</head>','<style id="agents25css">'+(r/'xxv/ui.css').read_text()+'</style></head>')
for tag,directive in [('script','script-src'),('style','style-src')]:
 contents=re.findall(r'<'+tag+r'(?:\s[^>]*)?>([\s\S]*?)</'+tag+'>',h)
 hashes=["'sha256-"+base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()+"'" for s in contents]
 h=re.sub(directive+r' [^;]+',directive+' '+' '.join(hashes),h,count=1)
h=re.sub(r"worker-src [^;]+","worker-src blob:",h,count=1) if 'worker-src ' in h else h.replace("; style-src","; worker-src blob:; style-src",1)
(r/'HARPOON_XXV.html').write_text(h)
(r/'HARPOON_XXV_3.html').write_text(h)
