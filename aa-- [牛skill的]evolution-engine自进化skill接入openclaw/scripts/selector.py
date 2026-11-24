#!/usr/bin/env python3
"""Select, apply, and rollback mutation candidates."""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from version_manager import VersionManager


DEFAULT_CONFIG = {
    "mode": "balanced",
    "observation_period_hours": {
        "conservative": 72,
        "balanced": 24,
        "aggressive": 4,
    },
}


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("selector")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


LOGGER = _setup_logger()


class Selector:
    def __init__(self, workspace_root: str, config: Optional[Dict[str, Any]] = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.evolution_dir = self.workspace_root / "evolution"
        self.mutations_dir = self.evolution_dir / "mutations"
        self.hypotheses_dir = self.evolution_dir / "hypotheses"
        self.config_path = self.evolution_dir / "config.yaml"
        self.version_manager = VersionManager(str(self.workspace_root))

        loaded = config if isinstance(config, dict) else self._load_config()
        self.mode = str(loaded.get("mode", "balanced"))
        self.observation_period = int(
            loaded.get("observation_period_hours", {}).get(
                self.mode, DEFAULT_CONFIG["observation_period_hours"]["balanced"]
            )
        )

    def select(self, evaluation: Dict[str, Any], hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        risk = str(hypothesis.get("risk", "medium"))
        confidence = float(hypothesis.get("confidence", 0.5))

        if evaluation.get("overall") == "fail":
            decision = "reject"
        elif risk == "critical":
            decision = "requires_approval"
        elif risk == "high" and confidence < 0.8:
            decision = "requires_approval"
        elif self.mode == "conservative" and risk in {"high", "medium"}:
            decision = "requires_approval"
        elif self.mode == "aggressive" and risk != "critical":
            decision = "auto_approve"
        elif risk == "low" and confidence >= 0.7:
            decision = "auto_approve"
        elif risk == "medium" and confidence >= 0.85:
            decision = "auto_approve"
        else:
            decision = "requires_approval"

        return {
            "mutation_id": evaluation.get("mutation_id"),
            "decision": decision,
            "reason": self._explain_decision(decision, risk, confidence, evaluation),
        }

    def apply(self, mutation: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        hypothesis = self._load_hypothesis_by_id(str(mutation.get("hypothesis_id", "")))
        if hypothesis is None:
            hypothesis = {"risk": "medium", "confidence": 0.5}

        simulated_eval = {"mutation_id": mutation.get("id"), "overall": "pass"}
        selection = self.select(simulated_eval, hypothesis)
        if selection["decision"] == "requires_approval" and not force:
            return {
                "mutation_id": mutation.get("id"),
                "decision": "requires_approval",
                "reason": selection["reason"],
                "applied": False,
            }

        version_id = self.version_manager.create_snapshot(f"Pre-mutation: {mutation.get('id')}")
        files_applied: List[str] = []

        for info in self._iter_files(mutation):
            staging = Path(str(info.get("staging_path", "")))
            target = Path(str(info.get("target_path", "")))
            if not staging.exists():
                raise FileNotFoundError(f"Staging file missing: {staging}")

            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_suffix(target.suffix + ".tmp")
            shutil.copy2(staging, temp)
            os.replace(temp, target)
            files_applied.append(str(target))

        result = {
            "mutation_id": mutation.get("id"),
            "version_id": version_id,
            "decision": "auto_approve" if force else selection["decision"],
            "applied": True,
            "files_applied": files_applied,
            "applied_at": datetime.now().isoformat(),
            "observation_until": (datetime.now() + timedelta(hours=self.observation_period)).isoformat(),
        }
        self._mark_mutation_applied(mutation, result)
        return result

    def apply_by_mutation_id(self, mutation_id: str, force: bool = False) -> Dict[str, Any]:
        mutation_path = self.mutations_dir / f"{mutation_id}.json"
        if not mutation_path.exists():
            raise FileNotFoundError(f"Mutation not found: {mutation_id}")
        mutation = json.loads(mutation_path.read_text(encoding="utf-8"))
        return self.apply(mutation, force=force)

    def rollback(self, version_id: str) -> Dict[str, Any]:
        success = self.version_manager.restore_snapshot(version_id)
        return {
            "version_id": version_id,
            "success": success,
            "rolled_back_at": datetime.now().isoformat(),
        }

    def _iter_files(self, mutation: Dict[str, Any]) -> List[Dict[str, Any]]:
        files: List[Dict[str, Any]] = []
        for key in ["files_created", "files_modified"]:
            entries = mutation.get(key, [])
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict):
                        files.append(entry)
        return files

    def _explain_decision(
        self, decision: str, risk: str, confidence: float, evaluation: Dict[str, Any]
    ) -> str:
        if decision == "reject":
            return f"Evaluation failed: {evaluation.get('recommendation', 'unknown reason')}"
        if decision == "auto_approve":
            return f"Mode={self.mode}, risk={risk}, confidence={confidence:.2f} meets auto-approve rules."
        return f"Mode={self.mode}, risk={risk}, confidence={confidence:.2f} requires manual approval."

    def _load_hypothesis_by_id(self, hypothesis_id: str) -> Optional[Dict[str, Any]]:
        if not hypothesis_id:
            return None
        for path in self.hypotheses_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            hypotheses = payload.get("hypotheses", [])
            if not isinstance(hypotheses, list):
                continue
            for hypothesis in hypotheses:
                if isinstance(hypothesis, dict) and str(hypothesis.get("id")) == hypothesis_id:
                    return hypothesis
        return None

    def _mark_mutation_applied(self, mutation: Dict[str, Any], apply_result: Dict[str, Any]) -> None:
        mutation_id = str(mutation.get("id", ""))
        if not mutation_id:
            return

        updated = dict(mutation)
        updated["status"] = "applied"
        updated["apply_result"] = apply_result

        by_id = self.mutations_dir / f"{mutation_id}.json"
        self._atomic_write_text(by_id, json.dumps(updated, ensure_ascii=False, indent=2))

        date_file = self.mutations_dir / f"{datetime.now().strftime('%Y-%m-%d')}.json"
        if not date_file.exists():
            return

        payload = json.loads(date_file.read_text(encoding="utf-8"))
        records = payload.get("mutations", [])
        if isinstance(records, list):
            for idx, record in enumerate(records):
                if isinstance(record, dict) and str(record.get("id")) == mutation_id:
                    records[idx] = updated
                    break
            payload["mutations"] = records
            self._atomic_write_text(date_file, json.dumps(payload, ensure_ascii=False, indent=2))

    def _load_config(self) -> Dict[str, Any]:
        config: Dict[str, Any] = {
            "mode": DEFAULT_CONFIG["mode"],
            "observation_period_hours": dict(DEFAULT_CONFIG["observation_period_hours"]),
        }
        if not self.config_path.exists():
            return config

        current_mode = config["mode"]
        active_mode: Optional[str] = None
        in_modes = False

        for raw in self.config_path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].rstrip()
            if not line.strip():
                continue

            stripped = line.strip()
            if stripped.startswith("mode:"):
                current_mode = stripped.split(":", 1)[1].strip()
                config["mode"] = current_mode
                continue

            if stripped == "modes:":
                in_modes = True
                continue

            if not in_modes:
                continue

            if line.startswith("  ") and stripped.endswith(":") and not stripped.startswith("observation_period_hours"):
                active_mode = stripped[:-1]
                continue

            if active_mode and "observation_period_hours:" in stripped:
                value = stripped.split(":", 1)[1].strip()
                if value.isdigit():
                    config["observation_period_hours"][active_mode] = int(value)

        return config

    def _atomic_write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(content, encoding="utf-8")
        os.replace(temp, path)


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent.parent.parent
    selector = Selector(str(root))
    print(
        json.dumps(
            {
                "ok": True,
                "mode": selector.mode,
                "observation_period_hours": selector.observation_period,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
