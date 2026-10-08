import unittest
import numpy as np
import pandas as pd
from risk_lab import backtest, drawdown, target_weights, validate, paired_bootstrap

class RiskTests(unittest.TestCase):
    def panel(self,n=90):
        return pd.DataFrame(np.random.default_rng(42).normal(.005,.03,(n,3)),
                 index=pd.period_range('2000-01',periods=n,freq='M').astype(str),columns=['Shops','A','B'])
    def test_future_change_does_not_change_current_weights(self):
        data=self.panel(); _,w=backtest(data,'Inverse volatility')
        changed=data.copy();changed.iloc[70:]=.5
        _,w2=backtest(changed,'Inverse volatility')
        np.testing.assert_allclose(w.iloc[:11],w2.iloc[:11])
    def test_first_loss_counts_in_drawdown(self):
        np.testing.assert_allclose(drawdown([-.1,1/9]),[-.1,0],atol=1e-12)
    def test_drift_and_transaction_cost(self):
        data=pd.DataFrame(0.,index=pd.period_range('2000-01',periods=14,freq='M').astype(str),columns=['Shops','A'])
        data.iloc[12,0]=1
        r,_=backtest(data,'Equal weight',lookback=12,cost_bps=10)
        self.assertAlmostEqual(r.iloc[0].traded_fraction,1)
        self.assertAlmostEqual(r.iloc[0].net_return,1.5*.999-1)
        self.assertAlmostEqual(r.iloc[1].traded_fraction,1/3)
    def test_var_uses_only_previous_months(self):
        data=self.panel();r,_=backtest(data,'Equal weight')
        changed=data.copy();changed.iloc[60]=-.8
        r2,_=backtest(changed,'Equal weight')
        self.assertEqual(r.iloc[0].forecast_var95,r2.iloc[0].forecast_var95)
    def test_gap_rejected(self):
        with self.assertRaises(ValueError):validate(self.panel().drop('2001-01'))
    def test_invalid_return_rejected(self):
        data=self.panel();data.iloc[2,0]=-1
        with self.assertRaises(ValueError):validate(data)
    def test_inverse_vol_weights(self):
        history=pd.DataFrame({'Shops':[.01,-.01,.02,-.02],'A':[.02,-.02,.04,-.04]})
        np.testing.assert_allclose(target_weights(history,'Inverse volatility'),[2/3,1/3])
    def test_weights_are_long_only_fully_invested(self):
        for name in ['Shops only','Equal weight','Inverse volatility']:
            _,w=backtest(self.panel(),name)
            self.assertTrue((w>=0).all().all());np.testing.assert_allclose(w.sum(axis=1),1)
    def test_paired_identical_series_has_zero_difference(self):
        data=self.panel().Shops
        np.testing.assert_allclose(paired_bootstrap(data,data,samples=100),[0,0])
    def test_common_start_charges_initial_purchase(self):
        for window in [36,60]:
            r,_=backtest(self.panel(),'Equal weight',lookback=window,start_month='2005-01')
            self.assertEqual(r.index[0],'2005-01');self.assertAlmostEqual(r.iloc[0].traded_fraction,1)
if __name__=='__main__':unittest.main()
