import os
import requests
import urllib3
from ..utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger('mirofish.services.hivemind')

class HivemindClient:
    """
    Direct bridge to the HIVEMIND Control Plane and Core API.
    Handles user profile extraction and secure metadata sync.
    """
    def __init__(self):
        pass

    @property
    def core_api_url(self):
        """Lazy — read env at call time, not import time."""
        raw = os.environ.get('HIVEMIND_API_URL') or 'https://core.hivemind.davinciai.eu:8050'
        # Ensure port 8050 is present (Caddy strips it on some deployments)
        if 'core.hivemind.davinciai.eu' in raw and ':8050' not in raw:
            raw = raw.replace('core.hivemind.davinciai.eu', 'core.hivemind.davinciai.eu:8050')
        return raw.rstrip('/')

    @property
    def control_plane_url(self):
        return os.environ.get('HIVEMIND_CONTROL_PLANE_URL', 'https://api.hivemind.davinciai.eu:8040')

    def validate_and_sync_profile(self, token):
        """
        Validates a HIVEMIND API key or session token.
        - API keys (hmk_live_*): validated via Core Server /api/memories (checks x-api-key)
        - Session tokens (UUID): validated via Control Plane /v1/bootstrap (checks Bearer)
        """
        try:
            if token.startswith('hmk_live_') or token.startswith('hmk_test_'):
                return self._validate_api_key(token)
            else:
                return self._validate_session_token(token)
        except Exception as e:
            logger.error(f"HivemindClient sync error: {str(e)}")
            return None

    def _validate_api_key(self, api_key):
        """Validate an API key via the HIVEMIND Core Server /api/profile."""
        try:
            profile_url = f"{self.core_api_url}/api/profile"
            logger.info(f"Validating API key via: {profile_url}")
            response = requests.get(
                profile_url,
                headers={"x-api-key": api_key},
                timeout=10,
                verify=False
            )

            if response.status_code == 200:
                data = response.json()
                profile = data.get('profile', {})
                user_id = profile.get('user_id', 'unknown')
                org_id = profile.get('org_id', 'personal')
                plan = profile.get('plan', 'free')
                memory_count = profile.get('memory_count', 0)

                return {
                    "user_id": user_id,
                    "organisation_id": org_id,
                    "display_name": f"HIVEMIND ({plan})",
                    "avatar_url": f"https://api.dicebear.com/7.x/bottts/svg?seed={user_id}",
                    "role": plan.capitalize(),
                    "memory_count": memory_count,
                    "status": "connected"
                }

            logger.error(f"HIVEMIND API key validation failed: {response.status_code} {response.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"API key validation error: {str(e)}")
            return None

    def _validate_session_token(self, token):
        """Validate a session token via the Control Plane bootstrap."""
        try:
            bootstrap_url = f"{self.control_plane_url}/v1/bootstrap"
            response = requests.get(
                bootstrap_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                user = data.get('user', {})
                org = data.get('organization', {})

                return {
                    "user_id": user.get('id'),
                    "organisation_id": org.get('id') if org else 'personal',
                    "display_name": user.get('display_name') or user.get('email', 'Unknown User'),
                    "avatar_url": user.get('avatar_url') or f"https://api.dicebear.com/7.x/bottts/svg?seed={user.get('id')}",
                    "role": user.get('role', 'Member'),
                    "status": "connected"
                }

            logger.error(f"HIVEMIND Bootstrap failed with status {response.status_code}: {response.text}")
            return None
        except Exception as e:
            logger.error(f"Session token validation error: {str(e)}")
            return None

    def persist_research_bundle(self, bundle_data):
        """
        Saves the compressed CSI bundle to the HIVEMIND Core database.
        """
        try:
            url = f"{self.core_api_url}/research/bundle/save"
            response = requests.post(url, json=bundle_data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to persist bundle to HIVEMIND Core: {str(e)}")
            return False
