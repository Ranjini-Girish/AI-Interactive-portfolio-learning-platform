import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["RLR_DATA_DIR"] = str(HERE / "environment" / "lockrank")
os.environ["RLR_AUDIT_DIR"] = str(HERE / "local-audit")
(HERE / "local-audit").mkdir(exist_ok=True)
src = (HERE / "solution" / "solve.sh").read_text(encoding="utf-8")
start = src.index("<<'PYEOF'") + len("<<'PYEOF'")
end = src.index("PYEOF\n", start)
exec(compile(src[start:end], str(HERE / "solution" / "solve.sh"), "exec"), {"__name__": "__main__"})
