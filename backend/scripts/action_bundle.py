import json
import os
import base64
import zlib
from datetime import datetime

class CSIPackager:
    """
    Compresses a CSI folder into a single portable JSON bundle 
    suitable for storage in the HIVEMIND database.
    """
    
    def __init__(self, simulation_id, base_dir="uploads/simulations"):
        self.simulation_id = simulation_id
        self.csi_dir = os.path.join(base_dir, simulation_id, "csi")
        
    def create_bundle(self, output_path=None):
        if not os.path.exists(self.csi_dir):
            raise FileNotFoundError(f"CSI directory not found: {self.csi_dir}")
            
        bundle = {
            "simulation_id": self.simulation_id,
            "timestamp": datetime.now().isoformat(),
            "files": {}
        }
        
        for filename in os.listdir(self.csi_dir):
            file_path = os.path.join(self.csi_dir, filename)
            if os.path.isfile(file_path):
                with open(file_path, "rb") as f:
                    content = f.read()
                    # Perform zlib compression (excellent for JSONL/text)
                    compressed = zlib.compress(content)
                    # Encode as base64 for JSON serialization
                    bundle["files"][filename] = base64.b64encode(compressed).decode('utf-8')
        
        serialized = json.dumps(bundle, ensure_ascii=False)
        
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(serialized)
            print(f"Bundle created: {output_path} ({len(serialized) / 1024:.2f} KB)")
            
        return serialized

    @staticmethod
    def extract_bundle(bundle_json, target_dir):
        """
        Reconstructs the CSI folder from a bundle string.
        """
        data = json.loads(bundle_json)
        sim_id = data["simulation_id"]
        csi_path = os.path.join(target_dir, sim_id, "csi")
        os.makedirs(csi_path, exist_ok=True)
        
        for filename, b64_content in data["files"].items():
            compressed = base64.b64decode(b64_content)
            content = zlib.decompress(compressed)
            with open(os.path.join(csi_path, filename), "wb") as f:
                f.write(content)
        
        print(f"Extraction complete for simulation: {sim_id}")
        return csi_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python action_bundle.py <simulation_id> [--extract]")
        sys.exit(1)
        
    sim_id = sys.argv[1]
    extract_mode = "--extract" in sys.argv
    
    packager = CSIPackager(sim_id)
    try:
        if extract_mode:
            bundle_path = f"uploads/simulations/{sim_id}/csi_bundle.json"
            target_dir = "uploads/simulations"
            with open(bundle_path, "r", encoding="utf-8") as f:
                bundle_json = f.read()
            # Rename existing csi to csi_old to verify extraction
            csi_path = os.path.join(target_dir, sim_id, "csi")
            if os.path.exists(csi_path):
                import shutil
                backup_path = csi_path + "_backup_" + datetime.now().strftime("%H%M%S")
                os.rename(csi_path, backup_path)
                print(f"Backed up existing csi to {backup_path}")
            
            packager.extract_bundle(bundle_json, target_dir)
        else:
            # Create a compressed snapshot in the uploads folder
            packager.create_bundle(output_path=f"uploads/simulations/{sim_id}/csi_bundle.json")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
