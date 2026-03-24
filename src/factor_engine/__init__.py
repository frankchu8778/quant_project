import sys
from pathlib import Path

# 僅在載入 factor_engine 時暫時加入，不影響其他模組
_ALPHAGEN_ROOT = Path("/home/newt/alphagen/alphagen-master/alphagen-master")
_path_added = False
if _ALPHAGEN_ROOT.exists():
    _root_str = str(_ALPHAGEN_ROOT)
    if _root_str not in sys.path:
        sys.path.insert(0, _root_str)
        _path_added = True

from .engine import FactorEngine

# 立刻移除，避免其他檔案從該目錄 import 到 dso / gplearn / factor_engine 等
if _path_added:
    sys.path.remove(_root_str)