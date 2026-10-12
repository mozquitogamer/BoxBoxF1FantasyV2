"""Immutable inputs for replaying future forecasts without today's mutable priors."""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _object(root, source):
    content = source.read_bytes()
    sha = hashlib.sha256(content).hexdigest()
    target = root / 'data/audit/objects' / (sha + source.suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if digest(target) != sha:
            raise ValueError(f'Corrupt replay object: {target.name}')
    else:
        with target.open('xb') as stream:
            stream.write(content)
    return {'source': source.relative_to(root).as_posix(),
            'object': target.relative_to(root).as_posix(), 'sha256': sha}


def freeze_inference_bundle(root, metadata, frames, sources):
    """Save exact, ordered feature frames and content-addressed public sources."""
    root = Path(root)
    directory = root / 'data/audit/inputs' / f"year{metadata['year']}" / f"round{metadata['round']}" / ('p_' + uuid4().hex[:16])
    directory.mkdir(parents=True, exist_ok=False)
    artifacts = []
    for name, frame in frames.items():
        if not name.replace('_', '').isalnum():
            raise ValueError('Invalid frame name')
        path = directory / (name + '.parquet')
        frame.to_parquet(path, index=True)
        artifacts.append({'path': path.relative_to(root).as_posix(), 'sha256': digest(path),
                          'rows': len(frame), 'columns': list(frame.columns)})
    objects = [_object(root, Path(source)) for source in sorted(set(sources)) if Path(source).is_file()]
    versions = {}
    for package in ['numpy', 'pandas', 'xgboost', 'fastf1', 'scipy']:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    payload = {'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
               'metadata': metadata, 'frames': artifacts, 'sources': objects, 'packages': versions}
    manifest = directory / 'manifest.json'
    with manifest.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, indent=2)
    return {'manifest': manifest.relative_to(root).as_posix(), 'sha256': digest(manifest)}


def freeze_simulation_inputs(root, metadata, frames, parameters):
    """Complete the same bundle with scoring inputs and resolved MC settings."""
    bundle = metadata.get('input_bundle')
    if not bundle:
        return None  # Forecasts generated before this feature cannot be reconstructed.
    root = Path(root)
    manifest = root / bundle['manifest']
    if not manifest.resolve().is_relative_to((root / 'data/audit/inputs').resolve()):
        raise ValueError('Replay bundle must be inside data/audit/inputs')
    if digest(manifest) != bundle['sha256']:
        raise ValueError('Inference manifest changed before simulation')
    # MC may be rerun with a new seed, calibration or scoring frame while the
    # model prediction stays the same. Preserve each invocation separately.
    directory = manifest.parent / ('s_' + uuid4().hex[:12])
    directory.mkdir(exist_ok=False)
    path = directory / 'simulation_inputs.json'
    artifacts = []
    for name, frame in frames.items():
        target = directory / (name + '.parquet')
        if target.exists():
            raise ValueError('Replay simulation frame already exists')
        frame.to_parquet(target, index=True)
        artifacts.append({'path': target.relative_to(root).as_posix(), 'sha256': digest(target)})
    with path.open('x', encoding='utf-8') as stream:
        json.dump({'schema_version': 1, 'inference_manifest': bundle,
                   'parameters': parameters, 'frames': artifacts}, stream, indent=2,
                  default=lambda value: value.tolist() if hasattr(value, 'tolist') else str(value))
    return path


def verify_inference_bundle(root, bundle):
    root = Path(root)
    manifest = root / bundle['manifest']
    if digest(manifest) != bundle['sha256']:
        return False
    payload = json.loads(manifest.read_text(encoding='utf-8'))
    return all(digest(root / row['path']) == row['sha256'] for row in payload['frames']) and all(
        digest(root / row['object']) == row['sha256'] for row in payload['sources'])
