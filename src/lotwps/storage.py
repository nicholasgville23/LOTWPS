from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class JSONStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.write({"messages": [], "alerts": [], "audit": []})

    def read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            value = {"messages": [], "alerts": [], "audit": []}
        return value if isinstance(value, dict) else {"messages": [], "alerts": [], "audit": []}

    def write(self, value: dict[str, Any]) -> None:
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
        temp.replace(self.path)

    def append(self, bucket: str, value: dict[str, Any]) -> None:
        data = self.read()
        data.setdefault(bucket, []).append({**value, "stored_at": datetime.now().astimezone().isoformat()})
        self.write(data)
