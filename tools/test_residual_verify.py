"""Synthetic mocked admission/derivation contracts; no ledger or real prices."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import residual_verify as rv
class Verification(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.p=self.root/'protocol.json';self.art=self.root/'art';self.art.mkdir()
  self.protocol={'dataset':'data/research_dataset.json'};self.data={'observed':'SYNTHETIC_CONTRACT_ONLY'};self.models={'counts':{'fit_invocations':2},'models':{'fixture':True}};self.signals={'signals':{}}
  (self.root/'data/raw').mkdir(parents=True);rv.write(self.p,self.protocol);rv.write(self.root/self.protocol['dataset'],self.data);rv.write(self.art/'models.json',self.models);rv.write(self.art/'signals.json',self.signals)
  for name,value in [('APP',self.root),('reg.verify',{'admission_identity_hash':'fixed'}),('admission.build_dataset',self.data),('model.fit_models',self.models),('model.generate_signals',self.signals)]:
   obj=patch('residual_verify.'+name,return_value=value) if '.' in name else patch('residual_verify.'+name,value);obj.start();self.addCleanup(obj.stop)
 def test_rebuilds_data_and_both_artifacts(self):
  r=rv.verify(self.p,self.art);self.assertTrue(r['verified']);self.assertEqual(r['fit_invocations'],2);self.assertEqual(set(r['hashes']),{'models.json','signals.json'})
 def test_preflight_does_not_fit(self):
  self.assertEqual(rv.verify(self.p)['fit_invocations'],0);rv.model.fit_models.assert_not_called()
 def test_refuses_before_read_or_fit_without_admission(self):
  rv.reg.verify.side_effect=ValueError('UNADMITTED');self.p.unlink()
  with self.assertRaisesRegex(ValueError,'UNADMITTED'):rv.verify(self.p,self.art)
  rv.admission.build_dataset.assert_not_called();rv.model.fit_models.assert_not_called()
 def test_changed_raw_dataset_refused(self):
  rv.admission.build_dataset.return_value={'modified':True}
  with self.assertRaisesRegex(ValueError,'RAW_DATASET_DERIVATION'):rv.verify(self.p,self.art)
 def test_changed_models_refused(self):
  rv.write(self.art/'models.json',{'modified':True})
  with self.assertRaisesRegex(ValueError,'DERIVATION_MISMATCH:models'):rv.verify(self.p,self.art)
 def test_changed_signals_refused(self):
  rv.write(self.art/'signals.json',{'modified':True})
  with self.assertRaisesRegex(ValueError,'DERIVATION_MISMATCH:signals'):rv.verify(self.p,self.art)
if __name__=='__main__':unittest.main()
