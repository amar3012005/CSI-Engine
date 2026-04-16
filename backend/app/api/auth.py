"""
Authentication and Profile Synchronization API
"Connect to HIVEMIND" - OAuth handshake via api.hivemind.davinciai.eu
"""

import os
from flask import request, jsonify
from . import auth_bp
from ..utils.logger import get_logger
from ..services.hivemind_client import HivemindClient

logger = get_logger('mirofish.api.auth')
hivemind = HivemindClient()

CONTROL_PLANE_URL = os.environ.get('HIVEMIND_CONTROL_PLANE_URL', 'https://api.hivemind.davinciai.eu:8040')


@auth_bp.route('/login-url', methods=['GET'])
def get_login_url():
    """
    Returns the HIVEMIND OAuth login URL for the frontend.
    The frontend can pass `?redirect=<callback_url>` to set the return address.
    """
    callback = request.args.get('redirect', '')
    if not callback:
        return jsonify({'error': 'redirect param required'}), 400

    login_url = f"{CONTROL_PLANE_URL}/auth/login?return_to={callback}"
    return jsonify({'login_url': login_url, 'control_plane': CONTROL_PLANE_URL})


@auth_bp.route('/sync', methods=['POST'])
def sync_profile():
    """
    Authentication Handshake & Profile Synchronization.
    Called by the frontend after returning from the HIVEMIND OAuth popup.
    Validates the session token with the HIVEMIND Control Plane's /v1/bootstrap.
    """
    try:
        data = request.get_json()
        token = data.get('token')

        if not token:
            return jsonify({'error': 'Token is required'}), 400

        logger.info("Syncing profile via HIVEMIND Control Plane...")
        profile = hivemind.validate_and_sync_profile(token)

        if not profile:
            logger.error("HIVEMIND sync failed for provided token.")
            return jsonify({'error': 'Invalid token or HIVEMIND sync failed. Please login again.'}), 401

        logger.info(f"Profile synced: {profile['display_name']} ({profile['user_id']})")
        return jsonify({'status': 'success', 'profile': profile})

    except Exception as e:
        logger.error(f"Profile sync failed: {str(e)}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/profile', methods=['GET'])
def get_profile():
    """
    Re-validates a stored session token and returns the latest profile.
    Useful for session refresh without a new OAuth flow.
    """
    token = request.headers.get('Authorization', '').replace('Bearer ', '').strip()
    if not token:
        return jsonify({'error': 'Bearer token required'}), 401

    profile = hivemind.validate_and_sync_profile(token)
    if not profile:
        return jsonify({'error': 'Token invalid or expired'}), 401

    return jsonify({'status': 'success', 'profile': profile})
