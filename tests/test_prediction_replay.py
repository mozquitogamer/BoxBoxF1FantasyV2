import json
import pandas as pd
from pipeline.prediction_replay import freeze_inference_bundle, verify_inference_bundle, freeze_simulation_inputs


def test_exact_frames_and_models_survive_mutable_source_updates(tmp_path):
    source = tmp_path / 'model.json';source.write_text('{"model":1}')
    frame = pd.DataFrame({'driver_id':['b','a'], 'pace':[float('nan'),91.1]},index=[8,3])
    metadata = {'year':2026,'round':19,'phase':'post_fp'}
    bundle = freeze_inference_bundle(tmp_path,metadata,{'qualifying':frame},[source])
    manifest = json.loads((tmp_path/bundle['manifest']).read_text())
    pd.testing.assert_frame_equal(pd.read_parquet(tmp_path/manifest['frames'][0]['path']),frame)
    source.write_text('{"model":2}')
    assert verify_inference_bundle(tmp_path,bundle)
    metadata['input_bundle'] = bundle
    path = freeze_simulation_inputs(tmp_path,metadata,{'fantasy':frame},{'seed':42,'calibration':{'noise_multiplier':1.3}})
    before = path.read_bytes()
    rerun = freeze_simulation_inputs(tmp_path,metadata,{'fantasy':frame},{'seed':999})
    assert rerun != path
    assert json.loads(rerun.read_text())['parameters']['seed'] == 999
    assert json.loads(path.read_text())['parameters']['seed'] == 42
    assert path.read_bytes() == before
    (tmp_path/manifest['sources'][0]['object']).write_text('corrupt')
    assert not verify_inference_bundle(tmp_path,bundle)
