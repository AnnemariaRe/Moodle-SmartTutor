import sys
from types import ModuleType
from unittest.mock import MagicMock

# Stub lightfm so that app.lightfm_model can be imported without the C library.
# Tests that need real LightFM inference use the actual model files saved to disk
# via joblib — those tests will fail gracefully if lightfm is absent.
if "lightfm" not in sys.modules:
    _lightfm_stub = ModuleType("lightfm")
    _lightfm_stub.LightFM = MagicMock  # type: ignore[attr-defined]
    sys.modules["lightfm"] = _lightfm_stub
    sys.modules["lightfm.evaluation"] = ModuleType("lightfm.evaluation")
