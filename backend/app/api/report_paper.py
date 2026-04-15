# report_paper.py
from flask import Blueprint, request, jsonify, stream_with_context
from app.services.paper_report_agent import PaperReportAgent
from app.services.report_agent import ReportManager, ReportStatus
from app.services.simulation_manager import SimulationManager
from app.models.project import ProjectManager
from app.services.zep_tools import ZepToolsService
from app.utils.logger import get_logger
import threading

logger = get_logger('mirofish.api.report_paper')
paper_report_bp = Blueprint('paper_report', __name__)

@paper_report_bp.route('/generate', methods=['POST'])
def generate_paper():
    data = request.json or {}
    simulation_id = data.get('simulation_id')
    graph_id = data.get('graph_id', '')
    simulation_requirement = data.get('simulation_requirement', 'Unspecified requirement')
    
    if not simulation_id:
        return jsonify({'error': 'simulation_id required'}), 400

    try:
        state = SimulationManager().get_simulation(simulation_id)
        if state:
            project = ProjectManager.get_project(state.project_id)
            if project and project.simulation_requirement:
                simulation_requirement = project.simulation_requirement
            graph_id = graph_id or state.graph_id or (project.graph_id if project else '')
    except Exception as exc:
        logger.warning("Failed to resolve simulation context for paper report: %s", exc)
        
    import uuid
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    
    def run_generation():
        try:
            agent = PaperReportAgent(graph_id, simulation_id, simulation_requirement)
            # generate_report returns the report and we need to save it. 
            # In ReportAgent it actually creates and saves the report if we pass report_id
            report = agent.generate_report(report_id=report_id)
            if "## References" not in (report.markdown_content or ""):
                try:
                    report.markdown_content = (
                        (report.markdown_content or "").rstrip()
                        + "\n\n"
                        + agent._build_ieee_references()
                        + "\n"
                    )
                except Exception as ref_exc:
                    logger.warning("Failed to append IEEE references: %s", ref_exc)
            report.report_type = 'ieee_paper'
            ReportManager.save_report(report)
        except Exception as e:
            logger.error(f"Paper report generation failed: {e}")
            
    thread = threading.Thread(target=run_generation)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True,
        'report_id': report_id,
        'data': {
            'report_id': report_id,
            'simulation_id': simulation_id,
            'status': 'planning'
        },
        'status': 'planning',
        'message': 'Paper generation started'
    })

@paper_report_bp.route('/by-simulation/<simulation_id>', methods=['GET'])
def get_paper_report_by_simulation(simulation_id):
    """Return the most recent paper report for a simulation."""
    try:
        reports = ReportManager.list_reports(simulation_id=simulation_id, limit=50)
        paper_report = next((report for report in reports if report.report_type in {'paper', 'ieee_paper'}), None)

        if not paper_report:
            paper_report = next(
                (
                    report for report in reports
                    if '[[Insight:' in (report.markdown_content or '')
                    or any('[[Insight:' in (section.content or '') for section in (report.outline.sections if report.outline else []))
                ),
                None,
            )

        if not paper_report:
            return jsonify({
                'success': False,
                'error': f'No paper report found for simulation: {simulation_id}',
                'has_report': False
            }), 404

        return jsonify({
            'success': True,
            'data': paper_report.to_dict(),
            'has_report': True
        })
    except Exception as e:
        logger.error(f"Failed to fetch paper report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@paper_report_bp.route('/insight/<claim_id>', methods=['GET'])
def get_insight(claim_id):
    """Fetch insight detail for a specific claim"""
    simulation_id = request.args.get('simulation_id')
    try:
        from app.services.simulation_csi_local import SimulationCSILocalStore
        store = SimulationCSILocalStore()
        
        # We need the simulation_id. If not passed, we have to look it up, which is hard.
        # But wait, maybe the frontend can pass it? The frontend has the report, and the report has simulation_id.
        if not simulation_id:
            logger.warning(f"No simulation_id provided for insight {claim_id}")
            # Try to grab it from somewhere or we can just scan all stores? 
            # LocalStore supports get(). 
            return jsonify({'error': 'simulation_id required'}), 400
            
        data = store.get(simulation_id)
        
        claims = data.get('claims', [])
        target_claim = next((c for c in claims if c.get('id') == claim_id), None)
        
        if not target_claim:
            return jsonify({'error': 'Claim not found'}), 404
            
        # Get trials supporting/contradicting
        trials = data.get('trials', [])
        supporting = [t for t in trials if t.get('claim_id') == claim_id and t.get('verdict') == 'supports']
        contradicting = [t for t in trials if t.get('claim_id') == claim_id and t.get('verdict') == 'contradicts']
        
        return jsonify({
            'success': True,
            'claim': target_claim,
            'stats': {
                'supporting_count': len(supporting),
                'contradicting_count': len(contradicting)
            }
        })
    except Exception as e:
        logger.error(f"Failed to fetch insight: {e}")
        return jsonify({'error': str(e)}), 500
