from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.ai_capability_audit import build_repo_ai_fallback_audit  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(build_repo_ai_fallback_audit(base_dir=ROOT), ensure_ascii=False, indent=2))
