import os
import json
import zlib
import base64
from datetime import datetime

import requests
import urllib3

from ..config import Config
from .simulation_csi_local import SimulationCSILocalStore
from ..utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger('mirofish.services.persistence')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hivemind_api_url() -> str:
    """Return the HIVEMIND Core API base URL (port 8050 enforced)."""
    raw = os.environ.get('HIVEMIND_API_URL') or os.environ.get('HIVEMIND_CORE_API_URL') or 'https://core.hivemind.davinciai.eu:8050'
    if 'core.hivemind.davinciai.eu' in raw and ':8050' not in raw:
        raw = raw.replace('core.hivemind.davinciai.eu', 'core.hivemind.davinciai.eu:8050')
    return raw.rstrip('/')


def _sim_base_dir(simulation_id: str) -> str:
    return os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)


def _read_json_file(path: str, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"Could not read {path}: {exc}")
        return default


def _read_profiles(sim_dir: str) -> dict:
    """Read agent profiles — prefers reddit_profiles.json, falls back to twitter_profiles.csv rows."""
    reddit_path = os.path.join(sim_dir, 'reddit_profiles.json')
    if os.path.exists(reddit_path):
        return _read_json_file(reddit_path, {})

    twitter_path = os.path.join(sim_dir, 'twitter_profiles.csv')
    if os.path.exists(twitter_path):
        try:
            import csv
            with open(twitter_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                return {"profiles": list(reader)}
        except Exception as exc:
            logger.warning(f"Could not read twitter_profiles.csv: {exc}")
    return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_full_bundle(simulation_id: str) -> dict:
    """
    Reads CSI state, report, config, and agent profiles from the local filesystem
    and builds a complete bundle dict compressed with zlib + base64.

    Returns a dict with keys:
      - simulation_id
      - query
      - timestamp
      - agents
      - csi_state
      - report
      - config
      - checkpoints
      - files           (compressed CSI directory files as base64 strings)
      - compressed      (zlib+base64 of the full bundle JSON, for HIVEMIND storage)
    """
    sim_dir = _sim_base_dir(simulation_id)
    csi_dir = os.path.join(sim_dir, 'csi')

    # --- CSI state ---------------------------------------------------------
    csi_store = SimulationCSILocalStore()
    csi_state = csi_store.get_state(simulation_id)

    # --- Simulation config -------------------------------------------------
    config_data = _read_json_file(os.path.join(sim_dir, 'simulation_config.json'), {})

    # --- Simulation state --------------------------------------------------
    state_data = _read_json_file(os.path.join(sim_dir, 'state.json'), {})

    # --- Report ------------------------------------------------------------
    report_data = _read_json_file(os.path.join(sim_dir, 'report.json'), {})
    if not report_data:
        # Try csi/ subdirectory
        report_data = _read_json_file(os.path.join(csi_dir, 'report.json'), {})

    # --- Agent profiles ----------------------------------------------------
    agents_data = _read_profiles(sim_dir)

    # --- CSI directory files (compressed individually, as in CSIPackager) --
    files: dict = {}
    if os.path.isdir(csi_dir):
        for filename in os.listdir(csi_dir):
            file_path = os.path.join(csi_dir, filename)
            if os.path.isfile(file_path):
                try:
                    with open(file_path, 'rb') as fh:
                        raw = fh.read()
                    compressed_file = zlib.compress(raw)
                    files[filename] = base64.b64encode(compressed_file).decode('utf-8')
                except Exception as exc:
                    logger.warning(f"Could not compress {filename}: {exc}")

    query = config_data.get('simulation_requirement') or config_data.get('query') or ''

    bundle = {
        'simulation_id': simulation_id,
        'query': query,
        'timestamp': datetime.now().isoformat(),
        'agents': agents_data,
        'csi_state': csi_state,
        'report': report_data,
        'config': config_data,
        'checkpoints': state_data.get('checkpoints', []),
        'files': files,
    }

    # Compress a lean version for HIVEMIND (exclude 'files' — raw CSI files are redundant with csi_state)
    lean_bundle = {k: v for k, v in bundle.items() if k != 'files'}
    lean_json = json.dumps(lean_bundle, ensure_ascii=False, default=str)
    compressed_bytes = zlib.compress(lean_json.encode('utf-8'))
    compressed_b64 = base64.b64encode(compressed_bytes).decode('utf-8')
    bundle['compressed'] = compressed_b64

    # Save a local copy for fast retrieval
    bundle_path = os.path.join(sim_dir, 'csi_bundle.json')
    try:
        with open(bundle_path, 'w', encoding='utf-8') as f:
            json.dump(bundle, f, ensure_ascii=False)
        logger.info(f"Local bundle saved: {bundle_path}")
    except Exception as exc:
        logger.warning(f"Could not save local bundle: {exc}")

    claim_count = len(csi_state.get('claims', [])) if isinstance(csi_state, dict) else 0
    source_count = len(csi_state.get('sources_index', {}).get('sources', [])) if isinstance(csi_state, dict) else 0
    logger.info(
        f"Bundle created for {simulation_id}: "
        f"{len(files)} CSI files, {claim_count} claims, {source_count} sources"
    )
    return bundle


def push_to_hivemind(simulation_id: str, compressed_bundle: str, metadata: dict, api_key: str) -> dict:
    """
    POSTs the compressed bundle to HIVEMIND as a single file on the 
    dedicated CSI memory endpoint.
    """
    if not api_key:
        return {'success': False, 'error': 'No API key provided'}

    url = f"{_hivemind_api_url()}/api/csi/bundle/{simulation_id}"
    query = metadata.get('query', '')
    title = f"CSI: {query[:80]}" if query else f"CSI session {simulation_id}"

    logger.info(f"Pushing bundle to HIVEMIND: {len(compressed_bundle)} chars")

    payload = {
        'simulation_id': simulation_id,
        'title': title,
        'content': compressed_bundle,
        'metadata': metadata
    }

    try:
        response = requests.post(
            url, json=payload,
            headers={
                'x-api-key': api_key,
                'Content-Type': 'application/json'
            },
            timeout=30, verify=False,
        )
        if response.status_code in (200, 201, 202):
            logger.info(f"Bundle pushed to HIVEMIND: {simulation_id}")
            return {'success': True, 'memory_id': simulation_id}

        logger.error(f"HIVEMIND push failed: {response.status_code} {response.text[:300]}")
        return {'success': False, 'error': f"HTTP {response.status_code}", 'detail': response.text[:300]}
    except Exception as exc:
        logger.error(f"HIVEMIND push error: {exc}")
        return {'success': False, 'error': str(exc)}


def get_bundle(simulation_id: str, api_key: str = '') -> dict:
    """
    Retrieves the bundle for a simulation.

    Priority:
      1. Local file  uploads/simulations/{sim_id}/csi_bundle.json
      2. HIVEMIND    GET /api/memories?tags=csi/bundle,session:{sim_id}

    Returns the bundle dict or raises FileNotFoundError.
    """
    sim_dir = _sim_base_dir(simulation_id)
    bundle_path = os.path.join(sim_dir, 'csi_bundle.json')

    # 1. Local cache
    if os.path.exists(bundle_path):
        try:
            with open(bundle_path, 'r', encoding='utf-8') as f:
                bundle = json.load(f)
            logger.info(f"Bundle loaded from local cache: {bundle_path}")
            return {'success': True, 'bundle': bundle, 'source': 'local'}
        except Exception as exc:
            logger.warning(f"Could not read local bundle {bundle_path}: {exc}")

    # 2. HIVEMIND — dedicated CSI bundle endpoint
    if not api_key:
        raise FileNotFoundError(f"Bundle not found locally for {simulation_id} and no API key for HIVEMIND lookup")

    url = f"{_hivemind_api_url()}/api/csi/bundle/{simulation_id}"
    try:
        response = requests.get(
            url,
            headers={'x-api-key': api_key},
            timeout=30,
            verify=False,
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('content'):
                compressed_b64 = data.get('content')
                bundle_json = zlib.decompress(base64.b64decode(compressed_b64)).decode('utf-8')
                bundle = json.loads(bundle_json)
                # Cache locally
                os.makedirs(sim_dir, exist_ok=True)
                with open(bundle_path, 'w', encoding='utf-8') as f:
                    json.dump(bundle, f, ensure_ascii=False)
                logger.info(f"Bundle retrieved from HIVEMIND and cached for {simulation_id}")
                return {'success': True, 'bundle': bundle, 'source': 'hivemind'}

        logger.warning(f"No HIVEMIND bundle found for {simulation_id}")
    except Exception as exc:
        logger.error(f"HIVEMIND get_bundle error: {exc}")
        raise FileNotFoundError(f"Bundle not found for {simulation_id}: {exc}") from exc

    raise FileNotFoundError(f"Bundle not found locally or in HIVEMIND for {simulation_id}")
