import importlib.util
from pathlib import Path


schema_path = Path(__file__).resolve().parents[1] / "app" / "services" / "csi_schema.py"
spec = importlib.util.spec_from_file_location("csi_schema", schema_path)
csi_schema = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(csi_schema)


def test_relation_type_preserves_needs_revision_verdict():
    assert csi_schema.relation_type_for_verdict("needs_revision") == "needs_revision"


def test_relation_type_preserves_support_and_contradiction_verdicts():
    assert csi_schema.relation_type_for_verdict("supports") == "supports"
    assert csi_schema.relation_type_for_verdict("contradicts") == "contradicts"


def test_relation_type_defaults_unknown_verdicts_to_needs_revision():
    assert csi_schema.relation_type_for_verdict("unclear") == "needs_revision"
    assert csi_schema.relation_type_for_verdict("") == "needs_revision"
