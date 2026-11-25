import unittest
from datetime import date,timedelta
from math import log1p
from ex71_replay import Episode
from ex71_advanced import robust_kelly,gain_exit

class AdvancedTests(unittest.TestCase):
    def test_kelly(self):
        d=date(2024,1,1)
        es=[Episode("TMF",d+timedelta(days=4*i),d+timedelta(days=4*i+1),log1p(.1)) for i in range(20)]
        w,u=robust_kelly(es,"TMF",d+timedelta(days=100),1/3)
        self.assertGreater(w,0)
        self.assertLessEqual(w,1/6)
        self.assertGreater(u,0)
        self.assertEqual(robust_kelly(es,"TMF",d,1/3),(0.,0.))
    def test_loss(self):
        self.assertEqual(gain_exit([.93],[0.,0.,0.],1),"loss_guard")
    def test_trail(self):
        self.assertEqual(gain_exit([1.1,1.06],[0.,0.,0.],2),"gain_trail")
    def test_hold(self):
        self.assertIsNone(gain_exit([1.2,1.17],[0.,0.,0.],2))
    def test_time(self):
        self.assertEqual(gain_exit([1.01],[0.,0.,0.],20),"time")
