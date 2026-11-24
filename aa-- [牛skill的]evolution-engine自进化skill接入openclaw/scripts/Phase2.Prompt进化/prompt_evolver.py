#!/usr/bin/env python3
"""Reflective prompt evolution for workspace guidance files."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class PromptEvolver:
    """反射式文本进化器"""

    EVOLVABLE_FILES: Dict[str, Dict[str, Any]] = {
        "SOUL.md": {
            "frozen_markers": ["不泄露隐私", "安全", "边界"],
            "max_change_pct": 0.3,
        },
        "AGENTS.md": {
            "frozen_markers": ["evolution:freeze", "安全策略", "权限控制"],
            "max_change_pct": 0.2,
        },
        "TOOLS.md": {
            "frozen_markers": [],
            "max_change_pct": 0.3,
        },
    }

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.evolution_dir = self.workspace_root / "evolution"
        self.staging_dir = self.evolution_dir / "staging"
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def analyze_failures(
        self,
        target_file: str,
        traces: List[Dict[str, Any]],
        eval_scores: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        target_path = self._resolve_target_file(target_file)
        content = target_path.read_text(encoding="utf-8")
        sections = self._split_sections(content)

        trace_items = self._normalize_traces(traces)
        failures = [item for item in trace_items if self._is_failure_trace(item)]
        if not failures:
            return {
                "target_file": target_file,
                "failure_analysis": [],
                "improvement_potential": 0.0,
                "num_failures": 0,
            }

        analyzed: List[Dict[str, Any]] = []
        for index, trace in enumerate(failures, start=1):
            task = self._extract_task(trace)
            failure = self._extract_failure(trace)
            relevant, relevance_score = self._match_relevant_section(sections, task, failure)
            section_title = relevant.get("title", "__unknown__")
            trace_id = str(trace.get("trace_id") or trace.get("id") or f"T{index:03d}")
            root_cause = self._derive_root_cause(task, failure, section_title)
            suggested_fix = self._suggest_fix(task, failure, section_title)

            analyzed.append(
                {
                    "trace_id": trace_id,
                    "task": task,
                    "failure": failure,
                    "relevant_section": section_title,
                    "root_cause": root_cause,
                    "suggested_fix": suggested_fix,
                    "relevance_score": round(relevance_score, 3),
                }
            )

        improvement_potential = self._estimate_improvement_potential(
            total=len(trace_items), failures=len(failures), eval_scores=eval_scores
        )

        return {
            "target_file": target_file,
            "failure_analysis": analyzed,
            "improvement_potential": round(improvement_potential, 4),
            "num_failures": len(failures),
        }

    def generate_variant(self, target_file: str, failure_analysis: Dict[str, Any]) -> Dict[str, Any]:
        target_path = self._resolve_target_file(target_file)
        original = target_path.read_text(encoding="utf-8")
        sections = self._split_sections(original)
        config = self.EVOLVABLE_FILES.get(target_file, {})
        max_change_pct = float(config.get("max_change_pct", 0.2))

        actions = self._collect_section_actions(failure_analysis)
        if not actions:
            return {
                "variant_path": "",
                "changes": [],
                "change_pct": 0.0,
                "reason": "No actionable failure analysis.",
            }

        updated = original
        changes: List[Dict[str, Any]] = []
        for section in sections:
            title = section.get("title", "")
            if title not in actions:
                continue
            snippet = section.get("content", "")
            if self._is_frozen(target_file, snippet, title):
                continue

            raw_fixes = actions.get(title, [])
            concise = [self._compress_fix(item) for item in raw_fixes if item]
            concise = [item for item in concise if item]
            if not concise:
                continue

            patch_block = self._render_patch_block(concise)
            section_content = section["content"]
            if "<!-- evolution:patch:start -->" in section_content:
                continue

            new_section_content = section_content.rstrip("\n") + patch_block
            updated = updated.replace(section_content, new_section_content, 1)
            changes.append(
                {
                    "section": title,
                    "type": "append",
                    "content": patch_block.strip(),
                }
            )

        if not changes:
            return {
                "variant_path": "",
                "changes": [],
                "change_pct": 0.0,
                "reason": "All candidate sections are frozen or unchanged.",
            }

        updated, changes = self._fit_change_budget(original, updated, changes, max_change_pct)
        if not changes:
            return {
                "variant_path": "",
                "changes": [],
                "change_pct": 0.0,
                "reason": "Unable to fit patch into change budget.",
            }
        change_pct = self._change_pct(original, updated)
        variant_path = self._write_variant(target_file, updated)

        return {
            "variant_path": str(variant_path),
            "changes": changes,
            "change_pct": round(change_pct, 4),
        }

    def _resolve_target_file(self, target_file: str) -> Path:
        if target_file not in self.EVOLVABLE_FILES:
            raise ValueError(f"Unsupported target file: {target_file}")
        path = self.workspace_root / target_file
        if not path.exists():
            raise FileNotFoundError(f"Target file not found: {path}")
        return path

    def _normalize_traces(self, traces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in traces:
            if isinstance(item, dict) and "traces" in item and isinstance(item["traces"], list):
                for trace in item["traces"]:
                    if isinstance(trace, dict):
                        normalized.append(trace)
            elif isinstance(item, dict):
                normalized.append(item)
        return normalized

    def _is_failure_trace(self, trace: Dict[str, Any]) -> bool:
        if trace.get("success") is False:
            return True
        failure_text = self._extract_failure(trace).lower()
        failure_markers = ["失败", "错误", "wrong", "regression", "didn't", "should", "bug"]
        return any(token in failure_text for token in failure_markers)

    def _extract_task(self, trace: Dict[str, Any]) -> str:
        for key in ("task", "task_input", "input", "user_request"):
            value = trace.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "未提供任务描述"

    def _extract_failure(self, trace: Dict[str, Any]) -> str:
        for key in ("failure", "user_feedback", "error", "output"):
            value = trace.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "未提供失败描述"

    def _match_relevant_section(
        self, sections: List[Dict[str, Any]], task: str, failure: str
    ) -> Tuple[Dict[str, Any], float]:
        text = f"{task}\n{failure}".lower()
        best: Optional[Dict[str, Any]] = None
        best_score = -1.0
        for section in sections:
            title = str(section.get("title", ""))
            body = str(section.get("content", ""))
            score = self._score_section(title, body, text)
            if score > best_score:
                best = section
                best_score = score
        return best or {"title": "__unknown__", "content": ""}, max(0.0, best_score)

    def _score_section(self, title: str, body: str, failure_text: str) -> float:
        title_low = title.lower()
        body_low = body.lower()
        score = 0.0

        title_tokens = [token for token in re.split(r"[\s/,_\-]+", title_low) if token]
        for token in title_tokens:
            if token and token in failure_text:
                score += 1.2

        keywords = [
            ("群聊", 2.0),
            ("heartbeat", 2.0),
            ("web", 1.2),
            ("memory", 1.0),
            ("红线", 1.6),
            ("session", 1.0),
            ("安全", 1.6),
            ("tool", 1.0),
        ]
        for keyword, weight in keywords:
            if keyword.lower() in failure_text and (keyword.lower() in title_low or keyword.lower() in body_low):
                score += weight

        overlap = 0
        for token in re.split(r"[^\w\u4e00-\u9fff]+", failure_text):
            if len(token) < 2:
                continue
            if token in title_low or token in body_low:
                overlap += 1
        score += min(3.0, overlap * 0.1)
        return score

    def _derive_root_cause(self, task: str, failure: str, section_title: str) -> str:
        failure_low = failure.lower()
        if "群聊" in section_title and ("有价值" in failure or "value" in failure_low):
            return "规则包含抽象表述，但缺乏可执行的判定标准，导致行为不稳定。"
        if "web" in section_title.lower() and ("skip" in failure_low or "没读" in failure):
            return "流程顺序约束存在，但缺少触发条件和错误分支说明。"
        if "heartbeat" in section_title.lower() and ("频繁" in failure or "spam" in failure_low):
            return "节奏规则缺少上限和抑制条件，导致过度执行。"
        return "关联段落的动作边界不够具体，执行时容易出现主观解释偏差。"

    def _suggest_fix(self, task: str, failure: str, section_title: str) -> str:
        if "群聊" in section_title:
            return "补充“有价值”判定条件：被@、明确求助、可避免重复错误时才主动发言。"
        if "Web Tools" in section_title or "web" in section_title.lower():
            return "补充失败分支：search/fetch失败必须先尝试opencli，再升级browser。"
        if "Heartbeat" in section_title:
            return "补充频率保护：同一轮仅一次HEARTBEAT_OK，且无新信息时保持静默。"
        if "Session启动" in section_title:
            return "补充缺失文件处理策略：不存在的记忆文件记为跳过并继续执行。"
        return "将抽象描述改为可判定规则（触发条件、禁止条件、优先级）。"

    def _estimate_improvement_potential(
        self, total: int, failures: int, eval_scores: Optional[Dict[str, Any]]
    ) -> float:
        if total <= 0:
            base = 0.0
        else:
            base = failures / float(total)
        if not eval_scores:
            return min(1.0, base)
        score = eval_scores.get("score") if isinstance(eval_scores, dict) else None
        if isinstance(score, (int, float)):
            return min(1.0, max(base, 1.0 - float(score)))
        return min(1.0, base)

    def _collect_section_actions(self, failure_analysis: Dict[str, Any]) -> Dict[str, List[str]]:
        records = failure_analysis.get("failure_analysis", [])
        result: Dict[str, List[str]] = {}
        if not isinstance(records, list):
            return result
        for item in records:
            if not isinstance(item, dict):
                continue
            section = str(item.get("relevant_section", "")).strip()
            fix = str(item.get("suggested_fix", "")).strip()
            if not section or not fix:
                continue
            result.setdefault(section, [])
            if fix not in result[section]:
                result[section].append(fix)
        return result

    def _compress_fix(self, text: str, max_len: int = 120) -> str:
        compact = " ".join(text.split())
        if len(compact) <= max_len:
            return compact
        return compact[: max_len - 1].rstrip() + "…"

    def _render_patch_block(self, fixes: List[str]) -> str:
        lines = ["", "<!-- evolution:patch:start -->", "### Evolution Patch", ""]
        for item in fixes[:3]:
            lines.append(f"- {item}")
        lines.extend(["<!-- evolution:patch:end -->", ""])
        return "\n".join(lines)

    def _fit_change_budget(
        self,
        original: str,
        updated: str,
        changes: List[Dict[str, Any]],
        max_change_pct: float,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        if self._change_pct(original, updated) <= max_change_pct:
            return updated, changes

        # Exceeding budget: keep only first change and trim to one line patch.
        if not changes:
            return original, []
        first = changes[0]
        section = str(first.get("section", ""))
        single_line = ""
        content = str(first.get("content", ""))
        for line in content.splitlines():
            if line.startswith("- "):
                single_line = line
                break
        if not single_line:
            single_line = "- 调整规则以提升可执行性。"

        sections = self._split_sections(original)
        fallback = original
        for section_item in sections:
            if section_item.get("title") != section:
                continue
            patch = "\n<!-- evolution:patch:start -->\n### Evolution Patch\n\n"
            patch += f"{single_line}\n<!-- evolution:patch:end -->\n"
            new_body = section_item["content"].rstrip("\n") + patch
            fallback = fallback.replace(section_item["content"], new_body, 1)
            break

        if self._change_pct(original, fallback) > max_change_pct:
            return original, []
        return fallback, [{**first, "content": patch.strip()}]

    def _change_pct(self, before: str, after: str) -> float:
        if not before:
            return 1.0 if after else 0.0
        length_delta = abs(len(after) - len(before))
        if length_delta == 0:
            return 0.0 if before == after else 0.01
        return min(1.0, length_delta / max(1, len(before)))

    def _write_variant(self, target_file: str, content: str) -> Path:
        stem = Path(target_file).stem
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = self.staging_dir / f"{stem}_variant_{ts}.md"
        tmp = out.with_suffix(".md.tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, out)
        return out

    def _is_frozen(self, target_file: str, content: str, section: str) -> bool:
        markers = self.EVOLVABLE_FILES.get(target_file, {}).get("frozen_markers", [])
        area = f"{section}\n{content}"
        return any(marker in area for marker in markers)

    def _split_sections(self, content: str) -> List[Dict[str, Any]]:
        lines = content.splitlines(keepends=True)
        heading_re = re.compile(r"^#{1,6}\s+")
        heading_positions = [idx for idx, line in enumerate(lines) if heading_re.match(line)]

        sections: List[Dict[str, Any]] = []
        if not heading_positions:
            return [{"title": "__document__", "content": content}]

        if heading_positions[0] > 0:
            preamble = "".join(lines[: heading_positions[0]])
            sections.append({"title": "__preamble__", "content": preamble})

        for index, start in enumerate(heading_positions):
            end = heading_positions[index + 1] if index + 1 < len(heading_positions) else len(lines)
            block = "".join(lines[start:end])
            title_line = lines[start].strip()
            title = re.sub(r"^#{1,6}\s*", "", title_line).strip()
            sections.append({"title": title, "content": block})
        return sections


def load_traces_file(path: str) -> List[Dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("traces"), list):
        return payload["traces"]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    raise ValueError(f"Unsupported traces payload: {path}")
