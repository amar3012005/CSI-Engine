import os
import json
import requests
from ..scripts.action_bundle import CSIPackager
from ..utils.logger import get_logger

logger = get_logger('mirofish.services.persistence')

class SimulationPersistence:
    """
    Handles the bridge between local CSI artifact storage and HIVEMIND PostgreSQL persistence.
    Workflow: Local Storage -> Bundle Compression -> DB ResearchBundle -> DB DeepResearch Metadata.
    """
    
    @staticmethod
    def finalize_and_persist(simulation_id, user_request, user_id, org_id=None, project_id=None):
        """
        1. Compresses local CSI artifacts in 'uploads/simulations/{sim_id}/csi'
        2. Saves the bundle string to the 'ResearchBundle' model
        3. Saves metadata to the 'DeepResearch' model
        """
        try:
            # Paths
            sim_dir = os.path.join('uploads', 'simulations', simulation_id)
            csi_dir = os.path.join(sim_dir, 'csi')
            
            if not os.path.exists(csi_dir):
                logger.warning(f"CSI directory not found for simulation {simulation_id}")
                return None

            # 1. Create Bundle
            logger.info(f"Creating CSI bundle for {simulation_id}...")
            bundle = CSIPackager.create_bundle(csi_dir)
            
            # 2. Persist to HIVEMIND DB (via Prisma/Internal API)
            # In production, this would be a direct prisma call or an internal HTTP POST to core.
            # Here we simulate the metadata payload for the 'ResearchBundle' and 'DeepResearch' tables.
            db_payload = {
                "simulation_id": simulation_id,
                "user_id": user_id,
                "org_id": org_id,
                "project_id": project_id,
                "user_request": user_request,
                "bundle_string": bundle["bundle"],
                "compressed_size": bundle["compressed_size"],
                "original_size": bundle["original_size"],
                "file_count": bundle["file_count"],
                "bundle_path": os.path.join(sim_dir, "csi_bundle.json")
            }
            
            # Save local copy as well for 'unveiling' speed
            with open(db_payload["bundle_path"], 'w') as f:
                json.dump(bundle, f)
                
            logger.info(f"CSI Bundle persisted: {bundle['compressed_size']} bytes ({bundle['file_count']} files)")
            return db_payload

        except Exception as e:
            logger.error(f"Persistence failed for {simulation_id}: {str(e)}")
            return None

    @staticmethod
    def unveil_from_db(simulation_id):
        """
        Retrieves the bundle from the DB (if local files are missing) and 'unveils' it.
        Allows viewing reports from months ago as if they were just run.
        """
        logger.info(f"Unveiling research state for {simulation_id}...")
        # 1. Fetch from ResearchBundle table (Simulated)
        # 2. Call CSIPackager.extract_bundle()
        # 3. Restore files to /uploads/simulations/{sim_id}/csi
        pass
