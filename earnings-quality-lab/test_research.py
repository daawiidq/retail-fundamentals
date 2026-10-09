import unittest
import numpy as np
import pandas as pd
from research import extract_company,make_panel,split_year,predict,bootstrap_difference,CFO,CONTROLS,FEATURES

def source():
    facts={}
    for tag,value in [(CFO,100),('NetIncomeLoss',120),('Assets',1000),('Liabilities',500)]:
        f={'accn':'original','end':'2019-12-31','filed':'2020-02-01','form':'10-K','val':value}
        if tag in [CFO,'NetIncomeLoss']:f['start']='2019-01-01'
        facts[tag]=[f]
    return {'ticker':'TEST','cik':1,'entityName':'Test','facts':facts}

class IntegrityTests(unittest.TestCase):
    def test_as_filed_not_later_revision(self):
        s=source()
        for tag,facts in s['facts'].items():
            facts.append({**facts[0],'accn':'revised','filed':'2020-03-01','val':999})
        r,e=extract_company(s)
        self.assertFalse(e);self.assertEqual(r[0]['cfo'],100);self.assertEqual(r[0]['accn'],'original')
    def test_income_duration_must_match(self):
        s=source();s['facts']['NetIncomeLoss'][0]['start']='2019-10-01'
        r,e=extract_company(s);self.assertFalse(r);self.assertIn('missing',e[0]['reason'])
    def test_missing_original_not_backfilled(self):
        s=source();s['facts']['NetIncomeLoss'][0]['accn']='later'
        r,e=extract_company(s);self.assertFalse(r)
    def test_conflicting_value_rejected(self):
        s=source();s['facts']['Assets'].append({**s['facts']['Assets'][0],'val':2000})
        r,e=extract_company(s);self.assertFalse(r);self.assertIn('conflicting',e[0]['reason'])
    def test_annual_not_quarterly_cfo(self):
        s=source();s['facts'][CFO][0]['start']='2019-10-01'
        r,e=extract_company(s);self.assertFalse(r)
    def test_features_hand_calculation(self):
        r,e=extract_company(source());self.assertAlmostEqual(r[0]['accruals_assets'],.02);self.assertAlmostEqual(r[0]['cfo_assets'],.1)
    def test_consolidated_income_preferred_with_tag_recorded(self):
        s=source();s['facts']['ProfitLoss']=[{**s['facts']['NetIncomeLoss'][0],'val':150}]
        r,e=extract_company(s);self.assertEqual(r[0]['income_tag'],'ProfitLoss');self.assertEqual(r[0]['net_income'],150)
    def test_conflicting_consolidated_income_cannot_fall_back(self):
        s=source();f=s['facts']['NetIncomeLoss'][0];s['facts']['ProfitLoss']=[{**f,'val':150},{**f,'val':155}]
        r,e=extract_company(s);self.assertFalse(r);self.assertIn('conflicting',e[0]['reason'])
    def test_cutoff_excludes_late_filings(self):
        r,e=extract_company(source(),'2019-12-31');self.assertFalse(r)
    def test_training_requires_label_available(self):
        p=pd.DataFrame({'filed':['2017-03-01','2017-04-01','2018-02-01'],
                        'label_filed':['2017-12-31','2018-02-01','2019-02-01']})
        train,test=split_year(p,2018);self.assertEqual(list(train.index),[0]);self.assertEqual(list(test.index),[2])
    def test_gap_not_treated_as_next_year(self):
        a=extract_company(source())[0][0]
        b={**a,'start':'2021-01-01','end':'2021-12-31','filed':'2022-02-01'}
        # make_panel currently expects at least one pair: construct one valid additional company.
        c={**a,'ticker':'OTHER'};d={**c,'start':'2020-01-01','end':'2020-12-31','filed':'2021-02-01','cfo_assets':.05}
        p=make_panel(pd.DataFrame([a,b,c,d]));self.assertEqual(list(p.ticker),['OTHER']);self.assertEqual(p.target.iloc[0],1)
    def test_future_values_do_not_affect_earlier_predictions(self):
        rng=np.random.default_rng(2);rows=[]
        for year in range(2010,2021):
            for firm in range(12):
                rows.append({'ticker':str(firm),'filed':f'{year}-03-01','label_filed':f'{year+1}-03-01',
                    'target':firm%2,**dict(zip(FEATURES,rng.normal(size=4)))})
        p=pd.DataFrame(rows);a=predict(p,[2018])[0]
        altered=p.copy();mask=altered.filed>='2019-01-01';altered.loc[mask,FEATURES]=1e8;altered.loc[mask,'target']=1
        b=predict(altered,[2018])[0]
        np.testing.assert_allclose(a.logit_accruals,b.logit_accruals)
    def test_bootstrap_identical_models_zero(self):
        p=pd.DataFrame({'ticker':['A','A','B','B'],'target':[0,1,1,0],
                        'logit_accruals':[.2,.7,.6,.3],'logit_controls':[.2,.7,.6,.3]})
        self.assertEqual(bootstrap_difference(p,'ticker',100)['ci95'],[0.,0.])
if __name__=='__main__':unittest.main()
