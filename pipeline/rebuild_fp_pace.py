"""Rebuild existing FP coverage offline with the current lap/feature policy.

Outputs are staged, never written over live features or historical forecasts.
Uses persisted FastF1 raw parquets, or the archived OpenF1 bundle identified
by a processed session's provenance sidecar. Does not fetch missing sessions.
"""
from __future__ import annotations
import argparse
import contextlib
import importlib
import io
import json
import sys
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config.settings import CURRENT_SEASON, FEATURES_DIR, FASTF1_RAW_DIR, LAPS_DIR, MIN_LONG_RUN_LAPS
from pipeline.fp_long_runs import FP_STINT_SEMANTICS_VERSION, require_fp_lap_semantics
from pipeline.import_openf1_fp import build_practice_laps

def rebuild(output: Path, only_events: set[str] | None = None) -> list[dict]:
    builder=importlib.import_module('pipeline.02_build_laps')
    extractor=importlib.import_module('pipeline.03_extract_features')
    driver_map,constructor_map=builder.load_id_mappings()
    feature_paths=sorted(FEATURES_DIR.glob('**/features.parquet'))
    report_path=output/'rebuild_report.json'
    report=json.loads(report_path.read_bytes()) if only_events and report_path.exists() else []
    for index,path in enumerate(feature_paths,1):
        year=int(path.parent.parent.name[4:]) if path.parent.parent.name.startswith('year') else CURRENT_SEASON
        rnd=int(path.parent.name.removeprefix('round'))
        if only_events and f'{year}:{rnd}' not in only_events:continue
        frames=[];sessions=[];sources=[];error=None
        try:
            raw_folder=FASTF1_RAW_DIR/f'year{year}'/f'round{rnd}'
            raw_paths=sorted(raw_folder.glob('fp[123].parquet'))
            bundles=sorted((ROOT/f'data/audit/inputs/year{year}/round{rnd}').glob('openf1_fp[123]_*'))
            if bundles:
                for bundle_path in bundles:
                    session_name=bundle_path.name.split('_')[1]
                    key=int(bundle_path.name.rsplit('_',1)[1])
                    session=next(s for s in json.loads((bundle_path/'sessions.json').read_bytes()) if s['session_key']==key)
                    if session['year']!=year or session['session_name']!=f'Practice {session_name[-1]}':
                        raise ValueError('Archived session identity mismatch')
                    if session_name.upper() in sessions:raise ValueError('Duplicate archived practice session')
                    bundle={n:json.loads((bundle_path/f'{n}_{session_name}.json').read_bytes())
                            for n in ['drivers','laps','stints','race_control','weather','session_result']}
                    frame=build_practice_laps(bundle,session,rnd)
                    frames.append(frame);sessions.append(session_name.upper());sources.append('openf1')
            elif raw_paths:
                for raw_path in raw_paths:
                    raw=pd.read_parquet(raw_path)
                    session_name=raw_path.stem.upper()
                    with contextlib.redirect_stdout(io.StringIO()):
                        frame=builder.structure_practice_laps(raw,pd.DataFrame(),year,rnd,session_name,
                                driver_map,constructor_map,track=str(raw['track'].iloc[0]) if 'track' in raw else '')
                    if frame is not None and not frame.empty:
                        frame['fp_data_source']='fastf1'
                        frames.append(frame);sessions.append(session_name);sources.append('fastf1')
            else:
                for sidecar in sorted((LAPS_DIR/f'round{rnd}').glob('fp[123]_source.json')):
                    provenance=json.loads(sidecar.read_bytes())
                    if provenance['session']['year']!=year:raise ValueError('Source year mismatch')
                    session_name=sidecar.stem.removesuffix('_source')
                    key=provenance['session']['session_key']
                    bundle_path=ROOT/f'data/audit/inputs/year{year}/round{rnd}/openf1_{session_name}_{key}'
                    bundle={n:json.loads((bundle_path/f'{n}_{session_name}.json').read_bytes())
                            for n in ['drivers','laps','stints','race_control','weather','session_result']}
                    frame=build_practice_laps(bundle,provenance['session'],rnd)
                    frames.append(frame);sessions.append(session_name.upper());sources.append('openf1')
            if not frames:raise ValueError('No archived raw practice sessions')
            for frame in frames:require_fp_lap_semantics(frame,source=f'{year}:{rnd}')
            combined=pd.concat(frames,ignore_index=True)
            feats=extractor.extract_driver_features(combined,MIN_LONG_RUN_LAPS)
            feats['year'],feats['round'],feats['fp_sessions_used']=year,rnd,len(frames)
            feats['fp_sessions_included']=','.join(sessions)
            feats['fp_data_sources']=','.join(sorted(set(sources)))
            feats['fp_stint_semantics_version']=FP_STINT_SEMANTICS_VERSION
            dest=output/'features'/path.relative_to(FEATURES_DIR)
            dest.parent.mkdir(parents=True,exist_ok=True)
            feats.to_parquet(dest,index=False)
            if year==CURRENT_SEASON:
                for frame,session_name in zip(frames,sessions):
                    dest=output/'laps'/f'round{rnd}'/f'all_laps_{session_name.lower()}.parquet'
                    dest.parent.mkdir(parents=True,exist_ok=True);frame.to_parquet(dest,index=False)
            row={'year':year,'round':rnd,'drivers':len(feats),'laps':len(combined),
                 'deleted_laps_retained':int(combined.lap_deleted.sum()),'sessions':sessions,'status':'ok'}
        except Exception as exc:
            row={'year':year,'round':rnd,'status':'failed','error':str(exc)}
        report=[r for r in report if (r['year'],r['round'])!=(year,rnd)]
        report.append(row)
        print(f'[{index}/{len(feature_paths)}] {row}',flush=True)
    output.mkdir(parents=True,exist_ok=True)
    (output/'rebuild_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    failed=[r for r in report if r['status']!='ok']
    if failed:raise RuntimeError(f'{len(failed)} events failed; staged rebuild is incomplete')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--only-events',help='Comma-separated YEAR:ROUND entries to retry')
    args=parser.parse_args()
    rebuild(args.output,set(args.only_events.split(',')) if args.only_events else None)
