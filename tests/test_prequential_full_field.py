import numpy as np
import pandas as pd
from pipeline import evaluate_prequential_2026 as pe

def test_test_field_keeps_retirements_until_after_position_ranking():
    df = pd.DataFrame({'season':[2026]*3,'round':[17]*3,'driver_id':['a','b','c'],
                       'quali_position':[1.,2.,3.], 'finish_position':[1.,2.,3.],
                       'is_finished':[1,1,0], 'is_dsq':[0]*3, 'is_dns':[0]*3})
    mask = pd.Series(True,index=df.index)
    auxiliary = pd.Series([2.,1.,3.])
    assert len(pe._eligible_rows(df,'race_fp',mask,auxiliary)) == 2
    field = pe._prediction_test_rows(df,'race_fp',mask,auxiliary)
    assert field.driver_id.tolist() == ['a','b','c']
    assert field.quali_position.tolist() == [2.,1.,3.]
    # The retired car can still rank ahead of finishers in a usable forecast.
    ranked = pe.scores_to_positions(np.array([2.,1.,3.]),field)
    assert ranked.tolist() == [2,3,1]
