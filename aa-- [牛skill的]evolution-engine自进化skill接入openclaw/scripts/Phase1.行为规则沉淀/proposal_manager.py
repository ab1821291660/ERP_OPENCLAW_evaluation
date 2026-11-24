#!/usr/bin/env python3
"""Proposal manager for Phase 1 evolution drafts and approval flow."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from gate_system import GateSystem
from version_manager import VersionManager


class ProposalManager:
    """Manage evolution proposals across pending/approved/rejected states."""

    DRAFT_DIR = "evolution-drafts"
    STATUS_DIRS = ["pending", "approved", "rejected"]

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.draft_root = self.workspace_root / self.DRAFT_DIR
        self.audit_dir = self.workspace_root / "evolution" / "audit"
        self.audit_file = self.audit_dir / "proposal_audit.log"
        self.version_manager = VersionManager(str(self.workspace_root))
        self._ensure_dirs()

    def create_proposal(
        self,
        signature: str,
        target_file: str,
        trigger_type: str,
        evidence: List[str],
        proposed_change: str,
        confidence: str,
        reason: str,
    ) -> Dict[str, Any]:
        normalized_signature = self._normalize_signature(signature)
        duplicate = self.check_duplicates(normalized_signature)
        if duplicate.get("is_duplicate", False):
            return {
                "ok": False,
                "action": duplicate.get("action", "skip"),
                "signature": normalized_signature,
                "duplicate": duplicate,
            }

        created_at = datetime.now().isoformat(timespec="seconds")
        payload = {
            "signature": normalized_signature,
            "target_file": self._normalize_target(target_file),
            "trigger_type": trigger_type,
            "evidence": evidence,
            "proposed_change": proposed_change.strip(),
            "confidence": confidence,
            "reason": reason.strip(),
            "status": "pending",
            "created_at": created_at,
            "updated_at": created_at,
        }
        path = self._proposal_path("pending", normalized_signature)
        self._write_proposal(path, payload)

        self._append_audit(
            {
                "event": "proposal_created",
                "signature": normalized_signature,
                "path": str(path),
                "target_file": payload["target_file"],
                "created_at": created_at,
            }
        )

        return {
            "ok": True,
            "action": "created",
            "signature": normalized_signature,
            "proposal_path": str(path),
            "status": "pending",
        }

    def evaluate_proposal(self, signature: str) -> Dict[str, Any]:
        normalized_signature = self._normalize_signature(signature)
        proposal = self._load_by_signature("pending", normalized_signature)
        if proposal is None:
            return {"ok": False, "error": f"Pending proposal not found: {normalized_signature}"}

        target_path = self.workspace_root / proposal["target_file"]
        if not target_path.exists():
            return {"ok": False, "error": f"Target file missing: {target_path}"}

        baseline_content = target_path.read_text(encoding="utf-8")
        variant_content = self._apply_change_text(baseline_content, proposal["proposed_change"], normalized_signature)

        eval_runner_result: Optional[Dict[str, Any]] = None
        eval_runner_error: Optional[str] = None
        eval_runner_used = False
        target_rel = str(proposal.get("target_file", "")).replace("\\", "/")
        if target_rel.startswith("skills/"):
            temp_dir = self.workspace_root / "evolution" / "tmp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_variant = temp_dir / f"{normalized_signature}_{target_path.name}"
            temp_variant.write_text(variant_content, encoding="utf-8")
            try:
                from eval_runner import EvalRunner

                runner = EvalRunner(str(self.workspace_root))
                eval_runner_result = runner.run_evaluation(
                    skill_path=str(target_path),
                    variant_path=str(temp_variant),
                    judge_mode="auto",
                )
                eval_runner_used = True
            except Exception as exc:
                eval_runner_error = str(exc)

        gate = GateSystem()
        gates = gate.run_all_gates(
            variant_content=variant_content,
            baseline_content=baseline_content,
            variant_scores={"total_score": 1.0, "dimensions": {"quality": 1.0, "safety": 1.0}},
            baseline_scores={"total_score": 1.0, "dimensions": {"quality": 1.0, "safety": 1.0}},
            target_type=self._target_type(target_path),
        )
        if eval_runner_result and isinstance(eval_runner_result.get("gates"), dict):
            gates = eval_runner_result["gates"]

        proposal["evaluation"] = {
            "evaluated_at": datetime.now().isoformat(timespec="seconds"),
            "gates": gates,
            "eval_runner_used": eval_runner_used,
            "eval_runner_error": eval_runner_error,
            "eval_runner_result": eval_runner_result,
            "passed": bool(gates.get("passed", False)),
        }
        proposal["updated_at"] = datetime.now().isoformat(timespec="seconds")

        if proposal["evaluation"]["passed"]:
            self._write_proposal(self._proposal_path("pending", normalized_signature), proposal)
            self._append_audit(
                {
                    "event": "proposal_evaluated",
                    "signature": normalized_signature,
                    "passed": True,
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
            )
            return {
                "ok": True,
                "signature": normalized_signature,
                "status": "pending",
                "evaluation": proposal["evaluation"],
            }

        reject_reason = self._extract_reject_reason(gates)
        rejected = self.reject_proposal(normalized_signature, reason=f"evaluation_failed: {reject_reason}")
        return {
            "ok": True,
            "signature": normalized_signature,
            "status": "rejected",
            "evaluation": proposal["evaluation"],
            "rejected": rejected,
        }

    def approve_proposal(self, signature: str) -> Dict[str, Any]:
        normalized_signature = self._normalize_signature(signature)
        proposal = self._load_by_signature("pending", normalized_signature)
        if proposal is None:
            return {"ok": False, "error": f"Pending proposal not found: {normalized_signature}"}

        target_path = self.workspace_root / proposal["target_file"]
        if not target_path.exists():
            return {"ok": False, "error": f"Target file missing: {target_path}"}

        snapshot_id = self.version_manager.create_snapshot(
            description=f"proposal:{normalized_signature} target:{proposal['target_file']}"
        )

        baseline = target_path.read_text(encoding="utf-8")
        updated = self._apply_change_text(baseline, proposal["proposed_change"], normalized_signature)
        temp = target_path.with_suffix(target_path.suffix + ".tmp")
        temp.write_text(updated, encoding="utf-8")
        os.replace(temp, target_path)

        proposal["status"] = "approved"
        proposal["approved_at"] = datetime.now().isoformat(timespec="seconds")
        proposal["version_backup"] = snapshot_id
        proposal["updated_at"] = proposal["approved_at"]

        approved_path = self._proposal_path("approved", normalized_signature)
        self._write_proposal(approved_path, proposal)

        pending_path = self._proposal_path("pending", normalized_signature)
        if pending_path.exists():
            pending_path.unlink()

        self._append_audit(
            {
                "event": "proposal_approved",
                "signature": normalized_signature,
                "target_file": proposal["target_file"],
                "version_backup": snapshot_id,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            }
        )

        return {
            "ok": True,
            "signature": normalized_signature,
            "status": "approved",
            "target_file": proposal["target_file"],
            "version_backup": snapshot_id,
            "proposal_path": str(approved_path),
        }

    def reject_proposal(self, signature: str, reason: Optional[str] = None) -> Dict[str, Any]:
        normalized_signature = self._normalize_signature(signature)
        proposal = self._load_by_signature("pending", normalized_signature)
        if proposal is None:
            return {"ok": False, "error": f"Pending proposal not found: {normalized_signature}"}

        proposal["status"] = "rejected"
        proposal["rejected_reason"] = reason or "manual_reject"
        proposal["rejected_at"] = datetime.now().isoformat(timespec="seconds")
        proposal["updated_at"] = proposal["rejected_at"]

        rejected_path = self._proposal_path("rejected", normalized_signature)
        self._write_proposal(rejected_path, proposal)

        pending_path = self._proposal_path("pending", normalized_signature)
        if pending_path.exists():
            pending_path.unlink()

        self._append_audit(
            {
                "event": "proposal_rejected",
                "signature": normalized_signature,
                "reason": proposal["rejected_reason"],
                "timestamp": proposal["rejected_at"],
            }
        )

        return {
            "ok": True,
            "signature": normalized_signature,
            "status": "rejected",
            "proposal_path": str(rejected_path),
            "reason": proposal["rejected_reason"],
        }

    def list_proposals(self, status: str = "pending") -> List[Dict[str, Any]]:
        normalized_status = status if status in self.STATUS_DIRS else "pending"
        items: List[Dict[str, Any]] = []
        for path in sorted((self.draft_root / normalized_status).glob("*.md")):
            payload = self._read_proposal(path)
            if payload:
                items.append(payload)
        items.sort(key=lambda item: str(item.get("updated_at", item.get("created_at", ""))), reverse=True)
        return items

    def check_duplicates(self, signature: str) -> Dict[str, Any]:
        normalized_signature = self._normalize_signature(signature)

        pending_path = self._proposal_path("pending", normalized_signature)
        if pending_path.exists():
            return {
                "is_duplicate": True,
                "existing_draft": str(pending_path),
                "existing_rule": None,
                "action": "update",
            }

        approved_path = self._proposal_path("approved", normalized_signature)
        if approved_path.exists():
            approved_payload = self._read_proposal(approved_path)
            existing_rule = self._find_existing_rule(approved_payload)
            return {
                "is_duplicate": True,
                "existing_draft": str(approved_path),
                "existing_rule": existing_rule,
                "action": "skip",
            }

        rejected_path = self._proposal_path("rejected", normalized_signature)
        if rejected_path.exists() and self._is_recent(rejected_path, days=14):
            return {
                "is_duplicate": True,
                "existing_draft": str(rejected_path),
                "existing_rule": None,
                "action": "skip",
            }

        return {
            "is_duplicate": False,
            "existing_draft": None,
            "existing_rule": None,
            "action": "create",
        }

    def _ensure_dirs(self) -> None:
        self.draft_root.mkdir(parents=True, exist_ok=True)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        for status in self.STATUS_DIRS:
            (self.draft_root / status).mkdir(parents=True, exist_ok=True)

    def _proposal_path(self, status: str, signature: str) -> Path:
        return self.draft_root / status / f"{self._normalize_signature(signature)}.md"

    def _normalize_signature(self, signature: str) -> str:
        lowered = signature.strip().lower()
        lowered = re.sub(r"[^a-z0-9\-_]+", "-", lowered)
        lowered = re.sub(r"-+", "-", lowered).strip("-")
        return lowered or f"proposal-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    def _normalize_target(self, target_file: str) -> str:
        normalized = target_file.strip().replace("\\", "/")
        if normalized.startswith("/"):
            normalized = str(Path(normalized).resolve().relative_to(self.workspace_root))
        return normalized

    def _write_proposal(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = self._proposal_to_markdown(payload)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(body, encoding="utf-8")
        os.replace(temp, path)

    def _read_proposal(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        match = re.search(r"```json\n(.*?)\n```", raw, flags=re.S)
        if not match:
            return None
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _load_by_signature(self, status: str, signature: str) -> Optional[Dict[str, Any]]:
        path = self._proposal_path(status, signature)
        return self._read_proposal(path)

    def _proposal_to_markdown(self, payload: Dict[str, Any]) -> str:
        return (
            f"# Evolution Proposal: {payload.get('signature', '')}\n\n"
            f"- Status: {payload.get('status', 'pending')}\n"
            f"- Target: {payload.get('target_file', '')}\n"
            f"- Trigger: {payload.get('trigger_type', '')}\n"
            f"- Confidence: {payload.get('confidence', '')}\n"
            f"- Created: {payload.get('created_at', '')}\n\n"
            "```json\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
            "```\n"
        )

    def _append_audit(self, event: Dict[str, Any]) -> None:
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        with self.audit_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _target_type(self, path: Path) -> str:
        if path.suffix.lower() == ".py":
            return "python"
        if path.name.upper() == "SKILL.MD":
            return "skill"
        return "prompt"

    def _extract_reject_reason(self, gates: Dict[str, Any]) -> str:
        details = gates.get("gates", {}) if isinstance(gates, dict) else {}
        chunks: List[str] = []
        for gate_name, gate_payload in details.items():
            if not isinstance(gate_payload, dict):
                continue
            if gate_payload.get("passed", False):
                continue
            gate_details = gate_payload.get("details", {})
            failures: List[str] = []
            if isinstance(gate_details, dict):
                if isinstance(gate_details.get("errors"), list):
                    failures.extend(gate_details.get("errors", []))
                if isinstance(gate_details.get("failures"), list):
                    failures.extend(gate_details.get("failures", []))
                if isinstance(gate_details.get("dimension_failures"), dict) and gate_details.get("dimension_failures"):
                    failures.append("dimension regression")
            chunk = f"{gate_name}:{'; '.join(failures) if failures else 'failed'}"
            chunks.append(chunk)
        return " | ".join(chunks) if chunks else "gate_failed"

    def _is_recent(self, path: Path, days: int) -> bool:
        cutoff = datetime.now() - timedelta(days=days)
        modified = datetime.fromtimestamp(path.stat().st_mtime)
        return modified >= cutoff

    def _find_existing_rule(self, proposal_payload: Optional[Dict[str, Any]]) -> Optional[str]:
        if not proposal_payload:
            return None

        target = proposal_payload.get("target_file")
        change = str(proposal_payload.get("proposed_change", "")).strip()
        if not target or not change:
            return None

        target_path = self.workspace_root / str(target)
        if not target_path.exists():
            return None

        content = target_path.read_text(encoding="utf-8")
        if change in content:
            return f"{target_path}: exact_change_present"
        signature = str(proposal_payload.get("signature", "")).strip()
        if signature and f"evolution-signature: {signature}" in content:
            return f"{target_path}: signature_marker_present"
        return None

    def _apply_change_text(self, baseline: str, change: str, signature: str) -> str:
        normalized_change = change.strip()
        if not normalized_change:
            return baseline

        signature_marker = f"evolution-signature: {signature}"
        if signature_marker in baseline or normalized_change in baseline:
            return baseline

        suffix = "\n" if baseline.endswith("\n") else "\n\n"
        block = (
            f"{suffix}<!-- {signature_marker} -->\n"
            f"{normalized_change}\n"
        )
        return baseline + block


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent.parent.parent
    manager = ProposalManager(str(root))
    print(json.dumps({"pending_count": len(manager.list_proposals('pending'))}, ensure_ascii=False, indent=2))
