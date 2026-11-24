#!/usr/bin/env python3
"""Apply mutation plans in staging area."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("mutator")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


LOGGER = _setup_logger()


class Mutator:
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.skill_root = self.workspace_root / "skills"
        self.engine_root = self.skill_root / "evolution-engine"
        self.evolution_dir = self.workspace_root / "evolution"
        self.staging_dir = self.evolution_dir / "staging"
        self.mutations_dir = self.evolution_dir / "mutations"
        self.hypotheses_dir = self.evolution_dir / "hypotheses"
        self.templates_dir = self.engine_root / "templates"

        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.mutations_dir.mkdir(parents=True, exist_ok=True)

    def mutate(self, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        action_type = str(hypothesis.get("action_type", "")).strip()
        hypothesis_id = str(hypothesis.get("id", "H000"))

        staging_root = self._create_staging(hypothesis_id)
        if action_type == "create_skill":
            result = self._create_skill(staging_root, hypothesis)
        elif action_type == "modify_skill_md":
            result = self._modify_skill_md(staging_root, hypothesis)
        elif action_type == "modify_skill_script":
            result = self._modify_skill_script(staging_root, hypothesis)
        elif action_type == "modify_memory":
            result = self._modify_text_file(staging_root, hypothesis, "MEMORY.md")
        elif action_type == "modify_agents":
            result = self._modify_text_file(staging_root, hypothesis, "AGENTS.md")
        elif action_type == "modify_soul":
            result = self._modify_text_file(staging_root, hypothesis, "SOUL.md")
        elif action_type == "modify_config":
            result = self._modify_text_file(staging_root, hypothesis, "evolution/config.yaml")
        elif action_type == "create_standing_order":
            result = self._create_standing_order(staging_root, hypothesis)
        elif action_type == "create_cron":
            result = self._create_cron(staging_root, hypothesis)
        else:
            raise ValueError(f"Unsupported action_type: {action_type}")

        mutation_id = f"M{int(datetime.now().timestamp() * 1000)}"
        mutation = {
            "id": mutation_id,
            "hypothesis_id": hypothesis_id,
            "action_type": action_type,
            "staging_path": str(staging_root),
            "files_created": result.get("files_created", []),
            "files_modified": result.get("files_modified", []),
            "created_at": datetime.now().isoformat(),
            "status": "staged",
            "before_after": result.get("before_after", []),
            "notes": result.get("notes", ""),
        }
        self._save_mutation(mutation)
        return mutation

    def mutate_by_hypothesis_id(self, hypothesis_id: str) -> Dict[str, Any]:
        hypothesis = self._load_hypothesis_by_id(hypothesis_id)
        if not hypothesis:
            raise FileNotFoundError(f"Hypothesis not found: {hypothesis_id}")
        return self.mutate(hypothesis)

    def _create_staging(self, hypothesis_id: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.staging_dir / f"{hypothesis_id}_{timestamp}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _create_skill(self, staging_root: Path, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        detail = hypothesis.get("action_detail", {})
        skill_name = str(detail.get("skill_name", "new-skill")).strip() or "new-skill"
        skill_name = self._sanitize_name(skill_name)

        target_skill_dir = self.skill_root / skill_name
        staging_skill_dir = staging_root / "skills" / skill_name
        staging_skill_dir.mkdir(parents=True, exist_ok=True)

        template_path = self.templates_dir / "skill_template.md"
        if template_path.exists():
            template = template_path.read_text(encoding="utf-8")
        else:
            template = "---\nname: {{skill_name}}\ndescription: {{description}}\n---\n\n# {{skill_name}}\n"

        skill_md = (
            template.replace("{{skill_name}}", skill_name)
            .replace("{{description}}", str(detail.get("description", "Auto-generated skill")))
            .replace("{{created_at}}", datetime.now().isoformat())
        )

        staging_skill_md = staging_skill_dir / "SKILL.md"
        self._atomic_write_text(staging_skill_md, skill_md)

        files_created: List[Dict[str, Any]] = [
            {
                "target_path": str(target_skill_dir / "SKILL.md"),
                "staging_path": str(staging_skill_md),
                "type": "file",
            }
        ]

        scripts_needed = detail.get("scripts", [])
        if isinstance(scripts_needed, list):
            for idx, script_name in enumerate(scripts_needed, start=1):
                sanitized = self._sanitize_name(str(script_name)).replace("-", "_")
                if not sanitized.endswith(".py"):
                    sanitized = f"{sanitized}.py"
                target_script = target_skill_dir / "scripts" / sanitized
                staging_script = staging_skill_dir / "scripts" / sanitized
                staging_script.parent.mkdir(parents=True, exist_ok=True)
                skeleton = self._script_skeleton(module_name=f"module_{idx}")
                self._atomic_write_text(staging_script, skeleton)
                files_created.append(
                    {
                        "target_path": str(target_script),
                        "staging_path": str(staging_script),
                        "type": "file",
                    }
                )

        return {
            "files_created": files_created,
            "files_modified": [],
            "notes": f"Created staged skill scaffold for {skill_name}.",
        }

    def _modify_skill_md(self, staging_root: Path, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        target_skill = self._select_existing_skill()
        if target_skill is None:
            return self._create_skill(staging_root, hypothesis)

        target_file = target_skill / "SKILL.md"
        if not target_file.exists():
            target_file.parent.mkdir(parents=True, exist_ok=True)
            original = "# SKILL\n"
        else:
            original = target_file.read_text(encoding="utf-8")

        addition = self._build_md_update(hypothesis)
        updated = f"{original.rstrip()}\n\n{addition}\n"

        staging_file = staging_root / target_file.relative_to(self.workspace_root)
        staging_file.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write_text(staging_file, updated)

        before_hash, after_hash = self._hash_text(original), self._hash_text(updated)
        return {
            "files_created": [],
            "files_modified": [
                {
                    "target_path": str(target_file),
                    "staging_path": str(staging_file),
                    "type": "file",
                }
            ],
            "before_after": [
                {
                    "target_path": str(target_file),
                    "before_hash": before_hash,
                    "after_hash": after_hash,
                }
            ],
            "notes": f"Staged SKILL.md update for {target_skill.name}.",
        }

    def _modify_skill_script(self, staging_root: Path, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        script_file = self._select_existing_script()
        if script_file is None:
            target_skill = self._select_existing_skill()
            if target_skill is None:
                return self._create_skill(staging_root, hypothesis)
            script_file = target_skill / "scripts" / "auto_patch.py"
            original = self._script_skeleton(module_name="auto_patch")
        else:
            original = script_file.read_text(encoding="utf-8")

        patch = self._build_script_patch(hypothesis)
        updated = f"{original.rstrip()}\n\n{patch}\n"

        staging_file = staging_root / script_file.relative_to(self.workspace_root)
        staging_file.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write_text(staging_file, updated)

        before_hash, after_hash = self._hash_text(original), self._hash_text(updated)
        return {
            "files_created": [],
            "files_modified": [
                {
                    "target_path": str(script_file),
                    "staging_path": str(staging_file),
                    "type": "file",
                }
            ],
            "before_after": [
                {
                    "target_path": str(script_file),
                    "before_hash": before_hash,
                    "after_hash": after_hash,
                }
            ],
            "notes": f"Staged script update for {script_file.name}.",
        }

    def _modify_text_file(self, staging_root: Path, hypothesis: Dict[str, Any], target_rel: str) -> Dict[str, Any]:
        target_file = self.workspace_root / target_rel
        target_file.parent.mkdir(parents=True, exist_ok=True)

        if target_file.exists():
            original = target_file.read_text(encoding="utf-8")
        else:
            original = ""

        detail = hypothesis.get("action_detail", {})
        change = str(detail.get("change", "Evolution engine generated an update."))
        updated = f"{original.rstrip()}\n\n- [evolution {datetime.now().isoformat()}] {change}\n"

        staging_file = staging_root / target_file.relative_to(self.workspace_root)
        staging_file.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write_text(staging_file, updated)

        return {
            "files_created": [],
            "files_modified": [
                {
                    "target_path": str(target_file),
                    "staging_path": str(staging_file),
                    "type": "file",
                }
            ],
            "before_after": [
                {
                    "target_path": str(target_file),
                    "before_hash": self._hash_text(original),
                    "after_hash": self._hash_text(updated),
                }
            ],
            "notes": f"Staged text update for {target_rel}.",
        }

    def _create_standing_order(self, staging_root: Path, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        target_file = self.workspace_root / "MEMORY.md"
        return self._modify_text_file(staging_root, hypothesis, str(target_file.relative_to(self.workspace_root)))

    def _create_cron(self, staging_root: Path, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        target_file = self.workspace_root / "evolution" / "cron.todo.md"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        detail = hypothesis.get("action_detail", {})
        rule = str(detail.get("rule", "Run evolution cycle daily."))
        original = target_file.read_text(encoding="utf-8") if target_file.exists() else "# Evolution Cron Plans\n"
        updated = f"{original.rstrip()}\n- {datetime.now().isoformat()} {rule}\n"

        staging_file = staging_root / target_file.relative_to(self.workspace_root)
        staging_file.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write_text(staging_file, updated)

        return {
            "files_created": [
                {
                    "target_path": str(target_file),
                    "staging_path": str(staging_file),
                    "type": "file",
                }
            ],
            "files_modified": [],
            "before_after": [
                {
                    "target_path": str(target_file),
                    "before_hash": self._hash_text(original),
                    "after_hash": self._hash_text(updated),
                }
            ],
            "notes": "Staged cron suggestion.",
        }

    def _load_hypothesis_by_id(self, hypothesis_id: str) -> Optional[Dict[str, Any]]:
        for file in self.hypotheses_dir.glob("*.json"):
            try:
                payload = json.loads(file.read_text(encoding="utf-8"))
            except Exception:
                continue

            for hypothesis in payload.get("hypotheses", []):
                if str(hypothesis.get("id")) == hypothesis_id:
                    return hypothesis
        return None

    def _select_existing_skill(self) -> Optional[Path]:
        if not self.skill_root.exists():
            return None

        for path in sorted(self.skill_root.iterdir()):
            if not path.is_dir():
                continue
            if path.name == "evolution-engine":
                continue
            if (path / "SKILL.md").exists():
                return path
        return None

    def _select_existing_script(self) -> Optional[Path]:
        skill = self._select_existing_skill()
        if skill is None:
            return None
        scripts_dir = skill / "scripts"
        if not scripts_dir.exists():
            return None
        for script in sorted(scripts_dir.rglob("*.py")):
            if script.is_file():
                return script
        return None

    def _build_md_update(self, hypothesis: Dict[str, Any]) -> str:
        detail = hypothesis.get("action_detail", {})
        change = str(detail.get("change", "Improve behavior consistency."))
        anchors = detail.get("anchors", [])
        lines = [
            "## Evolution Update",
            f"- Timestamp: {datetime.now().isoformat()}",
            f"- Hypothesis: {hypothesis.get('id', 'unknown')}",
            f"- Change: {change}",
        ]
        if isinstance(anchors, list) and anchors:
            lines.append(f"- Anchors: {', '.join(str(item) for item in anchors[:3])}")
        return "\n".join(lines)

    def _build_script_patch(self, hypothesis: Dict[str, Any]) -> str:
        return (
            "def evolution_guard(input_payload: dict) -> dict:\n"
            "    \"\"\"Auto-generated guard from Evolution Engine mutation.\"\"\"\n"
            "    if not isinstance(input_payload, dict):\n"
            "        return {\"ok\": False, \"error\": \"input_payload must be dict\"}\n"
            f"    return {{\"ok\": True, \"hypothesis_id\": \"{hypothesis.get('id', '')}\"}}"
        )

    def _script_skeleton(self, module_name: str) -> str:
        return (
            "#!/usr/bin/env python3\n"
            f"\"\"\"Auto-generated skeleton: {module_name}.\"\"\"\n\n"
            "from __future__ import annotations\n\n"
            "import json\n\n"
            "def main() -> int:\n"
            "    print(json.dumps({\"ok\": True, \"module\": \"auto\"}, ensure_ascii=False, indent=2))\n"
            "    return 0\n\n"
            "if __name__ == \"__main__\":\n"
            "    raise SystemExit(main())\n"
        )

    def _save_mutation(self, mutation: Dict[str, Any]) -> None:
        mutation_id = str(mutation.get("id", ""))
        now = datetime.now().strftime("%Y-%m-%d")

        by_id = self.mutations_dir / f"{mutation_id}.json"
        self._atomic_write_text(by_id, json.dumps(mutation, ensure_ascii=False, indent=2))

        by_day = self.mutations_dir / f"{now}.json"
        if by_day.exists():
            payload = json.loads(by_day.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                payload = {"date": now, "mutations": []}
        else:
            payload = {"date": now, "mutations": []}

        if "mutations" not in payload or not isinstance(payload.get("mutations"), list):
            payload["mutations"] = []
        payload["mutations"].append(mutation)
        self._atomic_write_text(by_day, json.dumps(payload, ensure_ascii=False, indent=2))
        LOGGER.info(f"Mutation saved: {mutation_id}")

    def _atomic_write_text(self, target: Path, text: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, target)

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _sanitize_name(self, raw: str) -> str:
        candidate = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw)
        candidate = "-".join(part for part in candidate.replace("_", "-").split("-") if part)
        return candidate.lower() or "generated-item"


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent.parent.parent
    mutator = Mutator(str(root))
    print(json.dumps({"ok": True, "message": "Use mutate_by_hypothesis_id from CLI."}, ensure_ascii=False, indent=2))
