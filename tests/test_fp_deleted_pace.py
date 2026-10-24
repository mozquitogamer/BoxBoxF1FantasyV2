"""Deleted FP times inform pace; pit/flag contamination and scoring do not."""
import importlib
import numpy as np
import pandas as pd
import pytest
from pipeline.fp_long_runs import FP_STINT_SEMANTICS_VERSION, require_fp_lap_semantics

builder=importlib.import_module('pipeline.02_build_laps')
extractor=importlib.import_module('pipeline.03_extract_features')

def test_fastf1_retains_deleted_times_but_not_pit_flag_or_nonpositive_laps():
    frame=pd.DataFrame({
        'LapTime':pd.to_timedelta([90,89,120,91,92,93,94,95,0,-1,None],unit='s'),
        'Deleted':[False,True,True,False,False,False,False,False,False,False,False],
        'PitInTime':[pd.NaT,pd.NaT,pd.Timedelta(1),pd.NaT,pd.NaT,pd.NaT,pd.NaT,pd.NaT,pd.NaT,pd.NaT,pd.NaT],
        'PitOutTime':[pd.NaT]*11,
        'TrackStatus':['1','1','1','4','5','6','7','12','1','1','1'],
    })
    clean=builder.clean_laps(frame)
    assert clean.index.tolist()==[0,1,7]
    assert clean.lap_deleted.tolist()==[False,True,False]
    assert builder.clean_laps(frame,include_deleted=False).index.tolist()==[0,7]

def test_deleted_flyer_and_sustained_run_reach_the_same_feature_extractor():
    raw=pd.DataFrame({
        'Driver':['VER']*7,'Team':['Red Bull Racing']*7,
        'LapTime':pd.to_timedelta([89,101,101.1,101.2,101.3,101.4,160],unit='s'),
        'Deleted':[True,False,True,False,True,False,False],
        'Compound':['SOFT']*7,'Stint':[1,2,2,2,2,2,2],
        'LapNumber':list(range(1,8)),'TyreLife':[2,3,4,5,6,7,8],
        'TrackStatus':['1']*7,
    })
    laps=builder.structure_practice_laps(raw,pd.DataFrame(),2026,20,'FP2',{'VER':'VER'},{'red bull racing':'red_bull'})
    require_fp_lap_semantics(laps,source='test')
    features=extractor.extract_driver_features(laps,5).set_index('driver_id')
    assert features.loc['VER','best_lap_time']==89
    assert features.loc['VER','long_run_laps']>=4
    assert 101<=features.loc['VER','long_run_avg']<102
    assert laps.lap_deleted.sum()==3

@pytest.mark.parametrize('stamp',[None,FP_STINT_SEMANTICS_VERSION-1,np.nan,FP_STINT_SEMANTICS_VERSION+.5])
def test_old_or_unstamped_lap_population_cannot_be_relabelled_as_new_features(stamp):
    frame=pd.DataFrame({'lap_time':[90]})
    if stamp is not None:frame['fp_lap_semantics_version']=stamp
    with pytest.raises(RuntimeError,match='rebuild laps from raw'):
        require_fp_lap_semantics(frame,source='old.parquet')
