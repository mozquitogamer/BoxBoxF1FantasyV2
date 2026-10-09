"""Identical inputs and RNG seed must work across Python hash seeds."""
import json
import os
import subprocess
import sys
from pathlib import Path

PROGRAM = r"""
import importlib.util,sys,json,hashlib
from pathlib import Path
import pandas as pd
import numpy as np
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
source=Path(sys.argv[2]) if len(sys.argv)>2 else root/'pipeline/08_monte_carlo_fantasy.py'
spec=importlib.util.spec_from_file_location('stable_mc',source);mc=importlib.util.module_from_spec(spec);spec.loader.exec_module(mc)
mc.load_overtake_history=lambda:{}
mc.load_drivers_info=lambda:{}
mc.load_mechanical_shares=lambda ids:np.full(len(ids),0.5)
pred=pd.DataFrame({'driver_id':list('abcdef'),'driver_abbrev':list('ABCDEF'),
 'constructor_id':['team_a','team_b','team_c']*2,'confidence':[70]*6,
 'predicted_quali_position':[1,2,3,4,5,6],'predicted_race_position':[2,1,3,5,4,6],
 'predicted_quali_raw':[3.,2.,1.,0.,-1.,-2.], 'predicted_race_raw':[2.,3.,1.,-1.,0.,-2.]})
fantasy=pd.DataFrame({'driver_id':list('abcdef'),'driver_abbrev':list('ABCDEF'),'dnf_probability':[0.2]*6})
result=mc.run_simulations(pred,fantasy,n_sims=300,seed=42)
h=hashlib.sha256()
for key,array in sorted(result['_sim_arrays'].items()):
 h.update(key.encode());value=np.asarray(array)
 h.update(json.dumps(value.tolist()).encode() if value.dtype.hasobject else value.tobytes())
print(json.dumps({'digest':h.hexdigest(),'order':result['simulation_params'].get('constructor_sampling_order')}))
"""


def run(seed, source=None):
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,PYTHONHASHSEED=str(seed),PYTHONIOENCODING='utf-8')
    command=[sys.executable,'-c',PROGRAM,str(root)]
    if source is not None:command.append(str(source))
    result=subprocess.run(command,capture_output=True,text=True,env=env,check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.splitlines()[-1])


def test_same_simulation_under_different_process_hash_seeds():
    first,second=run(1),run(7)
    assert first['digest']==second['digest']
    assert first['order']==['team_a','team_b','team_c']
