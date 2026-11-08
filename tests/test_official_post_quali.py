"""Published grids and banked DSQ scores must survive every race simulation."""
import importlib
import numpy as np
import pandas as pd
from config.post_quali import load_post_quali_results

mc = importlib.import_module('pipeline.08_monte_carlo_fantasy')
predict = importlib.import_module('pipeline.06_run_predictions')


def test_official_mexico_grid_and_disqualification():
    official = load_post_quali_results(21)
    drivers = official['drivers']
    assert drivers['lawson']['status'] == 'DSQ'
    assert drivers['lawson']['points'] == -5
    assert drivers['bortoleto']['grid'] == 13
    assert drivers['bottas']['grid'] == 21
    rows = pd.DataFrame({'driver_id': list(drivers), 'predicted_quali_position': list(range(1,23))})
    result = predict.build_race_grid_features(rows,
        {d:r['position'] for d,r in drivers.items()}, True,
        {'BOT': {'back_of_grid': True}}, {d:r['asset_id'] for d,r in drivers.items()},
        official_grid={d:r['grid'] for d,r in drivers.items()}).set_index('driver_id')
    assert result.loc['bottas','predicted_grid_position'] == 21
    assert result.loc['lawson','predicted_grid_position'] == 22
    assert result.loc['max_verstappen','quali_position'] == 4
    assert result.loc['max_verstappen','predicted_grid_position'] == 5
    assert load_post_quali_results(23) == {}


def test_official_brazil_grid_preserves_unpenalized_qualifying_points():
    official = load_post_quali_results(22)
    drivers = official['drivers']
    assert len(drivers) == 22 and len(official['constructors']) == 11
    assert (drivers['russell']['position'], drivers['russell']['grid'],
            drivers['russell']['points']) == (2, 7, 9)
    assert (drivers['leclerc']['position'], drivers['leclerc']['grid'],
            drivers['leclerc']['points']) == (4, 14, 7)
    assert drivers['hamilton']['grid'] == 20
    assert drivers['max_verstappen']['grid'] == 21
    assert drivers['perez']['grid'] == 22
    assert drivers['camara']['grid'] == 11


def test_dsq_and_constructor_points_are_fixed_in_every_simulation(monkeypatch):
    n = 4
    rows = pd.DataFrame({'driver_id': ['lin','law','bot','nor'], 'driver_abbrev': ['LIN','LAW','BOT','NOR'],
        'constructor_id': ['rb','rb','cadillac','mclaren'], 'confidence': [70]*n,
        'predicted_quali_position': [1,2,3,4], 'actual_quali_position': [1,4,3,2],
        'actual_quali_points': [10,-5,8,9], 'predicted_grid_position': [1,4,3,2],
        'predicted_race_position': [1,2,3,4], 'predicted_quali_raw': [3.,2.,1.,0.],
        'predicted_race_raw': [3.,2.,1.,0.]})
    fantasy = pd.DataFrame({'driver_abbrev': rows.driver_abbrev, 'dnf_probability': [0.0]*n})
    monkeypatch.setattr(mc,'load_overtake_history',lambda: {})
    monkeypatch.setattr(mc,'load_drivers_info',lambda: {})
    monkeypatch.setattr(mc,'load_mechanical_shares',lambda _: np.zeros(n))
    monkeypatch.setattr(mc,'official_pitstop_history',lambda: {})
    result=mc.run_simulations(rows,fantasy,n_sims=100,seed=21)
    arrays=result['_sim_arrays']
    assert result['simulation_params']['qualifying_locked']
    assert np.all(arrays['all_quali_pos'] == [1,4,3,2])
    assert np.all(arrays['all_quali_pts'] == [10,-5,8,9])
    info={d:{'driver_id':d,'constructor_id':'rb'} for d in ['LIN','LAW']}
    base=mc.aggregate_constructors(result['drivers'],info,{'rb':{'name':'RB'}},{'rb':6},sim_arrays=arrays,n_sims=100)
    banked=mc.aggregate_constructors(result['drivers'],info,{'rb':{'name':'RB'}},{'rb':6},sim_arrays=arrays,n_sims=100,banked_quali={'rb':-2})
    assert banked[0]['quali_bonus'] == -7
    assert abs((banked[0]['mc_total_mean']-base[0]['mc_total_mean']) - (-7-base[0]['quali_bonus'])) < .011
