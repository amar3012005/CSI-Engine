"""
CSI API路由
提供 CSI 数据摄取、判定、轨迹、蓝图与报告门控接口
"""

from flask import request, jsonify

from . import csi_bp


def _json_body():
    """Safely parse JSON body."""
    data = request.get_json(silent=True)
    if data is None:
        return {}, False
    if not isinstance(data, dict):
        return {}, False
    return data, True


def _require_fields(data, fields):
    """Return missing required fields."""
    missing = []
    for field in fields:
        value = data.get(field)
        if value is None:
            missing.append(field)
        elif isinstance(value, str) and not value.strip():
            missing.append(field)
    return missing


def _get_adapter():
    """
    Lazy-load CSIAdapter so this module can be registered even when adapter
    implementation is introduced in a later slice.
    """
    try:
        from ..services.csi_adapter import CSIAdapter  # pylint: disable=import-outside-toplevel
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    return CSIAdapter(), None


def _adapter_or_error():
    adapter, err = _get_adapter()
    if adapter is None:
        return None, (
            jsonify(
                {
                    "success": False,
                    "error": "CSIAdapter unavailable",
                    "details": err,
                }
            ),
            500,
        )
    return adapter, None


def _call_adapter(fn, *args, **kwargs):
    try:
        return True, fn(*args, **kwargs), None
    except ValueError as exc:
        return False, None, (jsonify({"success": False, "error": str(exc)}), 400)
    except Exception as exc:  # noqa: BLE001
        return False, None, (jsonify({"success": False, "error": "CSI internal error", "details": str(exc)}), 500)


@csi_bp.route('/sources/ingest', methods=['POST'])
def csi_ingest_sources():
    """
    POST /api/csi/sources/ingest
    Required: source(s) payload.
    """
    data, ok = _json_body()
    if not ok:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    if "source" not in data and "sources" not in data:
        return jsonify({
            "success": False,
            "error": "Missing required field: source or sources",
        }), 400

    adapter, error_response = _adapter_or_error()
    if error_response:
        return error_response

    ok_call, result, err = _call_adapter(adapter.ingest_sources, data)
    if not ok_call:
        return err
    return jsonify({"success": True, "data": result}), 200


@csi_bp.route('/claims/extract', methods=['POST'])
def csi_extract_claims():
    """
    POST /api/csi/claims/extract
    Required: source_id or extract_id or source_text.
    """
    data, ok = _json_body()
    if not ok:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    if not any(k in data for k in ("source_id", "extract_id", "source_text")):
        return jsonify({
            "success": False,
            "error": "Missing one of: source_id, extract_id, source_text",
        }), 400

    adapter, error_response = _adapter_or_error()
    if error_response:
        return error_response

    ok_call, result, err = _call_adapter(adapter.extract_claims, data)
    if not ok_call:
        return err
    return jsonify({"success": True, "data": result}), 200


@csi_bp.route('/claims/verdict', methods=['POST'])
def csi_claim_verdict():
    """
    POST /api/csi/claims/verdict
    Required: claim_id, verdict.
    """
    data, ok = _json_body()
    if not ok:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    missing = _require_fields(data, ["claim_id", "verdict"])
    if missing:
        return jsonify({
            "success": False,
            "error": "Missing required fields",
            "missing_fields": missing,
        }), 400

    adapter, error_response = _adapter_or_error()
    if error_response:
        return error_response

    ok_call, result, err = _call_adapter(adapter.record_verdict, data)
    if not ok_call:
        return err
    return jsonify({"success": True, "data": result}), 200


@csi_bp.route('/trails/log', methods=['POST'])
def csi_log_trail():
    """
    POST /api/csi/trails/log
    Required: trail.
    """
    data, ok = _json_body()
    if not ok:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    if "trail" not in data:
        return jsonify({
            "success": False,
            "error": "Missing required field: trail",
        }), 400

    adapter, error_response = _adapter_or_error()
    if error_response:
        return error_response

    ok_call, result, err = _call_adapter(adapter.log_trail, data)
    if not ok_call:
        return err
    return jsonify({"success": True, "data": result}), 200


@csi_bp.route('/blueprints/promote', methods=['POST'])
def csi_promote_blueprint():
    """
    POST /api/csi/blueprints/promote
    Required: trail_ids or trail_query.
    """
    data, ok = _json_body()
    if not ok:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    if "trail_ids" not in data and "trail_query" not in data:
        return jsonify({
            "success": False,
            "error": "Missing required field: trail_ids or trail_query",
        }), 400

    adapter, error_response = _adapter_or_error()
    if error_response:
        return error_response

    ok_call, result, err = _call_adapter(adapter.promote_blueprint, data)
    if not ok_call:
        return err
    return jsonify({"success": True, "data": result}), 200


@csi_bp.route('/report/gate-check', methods=['POST'])
def csi_gate_check():
    """
    POST /api/csi/report/gate-check
    Required: report_context.
    """
    data, ok = _json_body()
    if not ok:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    if "report_context" not in data:
        return jsonify({
            "success": False,
            "error": "Missing required field: report_context",
        }), 400

    adapter, error_response = _adapter_or_error()
    if error_response:
        return error_response

    ok_call, result, err = _call_adapter(adapter.gate_check, data)
    if not ok_call:
        return err
    return jsonify({"success": True, "data": result}), 200


@csi_bp.route('/report/generate', methods=['POST'])
def csi_generate_report():
    """
    POST /api/csi/report/generate
    Required: report_context.
    """
    data, ok = _json_body()
    if not ok:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    if "report_context" not in data:
        return jsonify({
            "success": False,
            "error": "Missing required field: report_context",
        }), 400

    adapter, error_response = _adapter_or_error()
    if error_response:
        return error_response

    ok_call, result, err = _call_adapter(adapter.generate_report, data)
    if not ok_call:
        return err
    return jsonify({"success": True, "data": result}), 200


@csi_bp.route('/report/<report_id>/provenance', methods=['GET'])
def csi_report_provenance(report_id: str):
    """
    GET /api/csi/report/<id>/provenance
    """
    if not report_id or not report_id.strip():
        return jsonify({"success": False, "error": "Invalid report_id"}), 400

    adapter, error_response = _adapter_or_error()
    if error_response:
        return error_response

    ok_call, result, err = _call_adapter(adapter.get_report_provenance, report_id)
    if not ok_call:
        return err
    if result is None:
        return jsonify({
            "success": False,
            "error": f"Report provenance not found: {report_id}",
        }), 404

    return jsonify({"success": True, "data": result}), 200
