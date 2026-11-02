"""No new financial trials: terminal-state and decision contracts."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'work/HarpoonX_Motor_Quant'))
from analyze import decide
from harpoon_quant.recursive import Journal

class WorkflowTests(unittest.TestCase):
 def test_relative_improvement_cannot_override_negative_profit(self):self.assertEqual(decide(-1,-.01,.1,True,True,True,True),'REJECTED')
 def test_positive_underpowered_not_accepted(self):self.assertEqual(decide(10,.01,.001,False,True,True,True),'INSUFFICIENT_EVIDENCE')
 def test_all_pass_still_synthetic_only(self):self.assertEqual(decide(10,.01,.001,True,True,True,True),'RESEARCH_ACCEPTED_SYNTHETIC_ONLY')
 def invoke(self,stage,mutation=None):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);study=root/'study';study.mkdir();(root/'evidence').mkdir()
   for n in ['protocol.json','optimizer.sqlite3']:shutil.copy2(ROOT/'study'/n,study/n)
   shutil.copy2(ROOT/'evidence/alpaca_calendar.json',root/'evidence/alpaca_calendar.json')
   if mutation=='protocol':
    x=json.loads((study/'protocol.json').read_text());x['capital']=40000;(study/'protocol.json').write_text(json.dumps(x))
   if mutation=='code':
    j=Journal(study/'optimizer.sqlite3')
    with j.transaction():j.put('economic:implementation',{'hash':'changed'},'2026-10-31T00:00:00Z')
    j.close()
   env=dict(os.environ,PYTHONPATH=str(ROOT/'work/HarpoonX_Motor_Quant'))
   r=subprocess.run([sys.executable,'-m','harpoon_quant.economic_lab',stage,'--directory',str(study)],env=env,cwd=root,capture_output=True,text=True)
   j=Journal(study/'optimizer.sqlite3');self.assertEqual(j.get('budget')['spent'],23);j.close();return r
 def test_holdout_cannot_be_spent_twice(self):
  r=self.invoke('holdout');self.assertNotEqual(r.returncode,0);self.assertIn('HOLDOUT_ALREADY_SPENT',r.stderr)
 def test_development_cannot_select_again(self):
  r=self.invoke('develop');self.assertNotEqual(r.returncode,0);self.assertIn('FINALIST_ALREADY_FROZEN',r.stderr)
 def test_changed_protocol_blocked(self):
  r=self.invoke('holdout','protocol');self.assertNotEqual(r.returncode,0);self.assertIn('REGISTERED_PROTOCOL_CHANGED',r.stderr)
 def test_changed_code_binding_blocked(self):
  r=self.invoke('holdout','code');self.assertNotEqual(r.returncode,0);self.assertIn('REGISTERED_CODE_CHANGED',r.stderr)
if __name__=='__main__':unittest.main()
