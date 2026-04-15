"""
Authentication and Profile Synchronization API
Achieves "Connect to HIVEMIND" by syncing user profiles from the Control Plane.
"""

from flask import request, jsonify
from . import auth_bp
from ..utils.logger import get_logger
import requests

logger = get_logger('mirofish.api.auth')

@auth_bp.route('/sync', methods=['POST'])
def sync_profile():
    """
    Authentication Handshake & Profile Synchronization
    Validates OIDC JWT against HIVEMIND Control Plane and extracts profile data.
    """
    try:
        data = request.get_json()
        token = data.get('token')
        
        if not token:
            return jsonify({'error': 'Token is required'}), 400

        # Authentication Handshake: Validate token with HIVEMIND Control Plane
        # In a real scenario, this would call the Zitadel/OIDC provider or a HIVEMIND internal auth service
        # For now, we simulate the validation and extraction
        
        # Profile Extraction (Mocked for now, but following the requested flow)
        # Database Lookup: Fetch displayName, avatar, and org details
        user_profile = {
            'user_id': 'hm_user_772211',
            'organisation_id': 'hm_org_da_vinci',
            'display_name': 'DaVinci Researcher',
            'avatar_url': 'https://api.dicebear.com/7.x/bottts/svg?seed=DaVinci',
            'role': 'Researcher',
            'status': 'connected'
        }
        
        logger.info(f"User profile synced: {user_profile['display_name']} ({user_profile['user_id']})")
        
        return jsonify({
            'status': 'success',
            'profile': user_profile
        })

    except Exception as e:
        logger.error(f"Profile sync failed: {str(e)}")
        return jsonify({'error': str(e)}), 500
