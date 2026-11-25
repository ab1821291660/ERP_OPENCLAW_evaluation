#!/usr/bin/env python3
"""Read saved lesson16 task evidence without starting Hermes or a model."""
import argparse
import difflib
import json
from pathlib import Path


def render(stage="origin"):
    data = json.loads((Path(__file__).parent / "materials/iteration-case.json").read_text())
    stages = data["stages"]
    if stage not in stages:
        raise ValueError("stage must be origin, candidate or revision")
    selected = stages[stage]
    titles = {"origin": "原版方法与 east 调查", "candidate": "原生修订与新现场回放",
              "revision": "审阅后修订与再次回放"}
    parts = [f"# {titles[stage]}",
             "2026-11-15 已保存的在线模型运行节选；Hermes 工具真实执行，业务现场为本讲构造数据。本命令不调用模型。"]
    if stage == "origin":
        parts += ["## 原方法", "```markdown\n" + selected["skill"] + "```"]
    else:
        previous = stages["origin" if stage == "candidate" else "candidate"]["skill"]
        diff = "".join(difflib.unified_diff(previous.splitlines(True), selected["skill"].splitlines(True),
                                             fromfile="before/SKILL.md", tofile="after/SKILL.md"))
        parts += ["## 同名方法的变化", "```diff\n" + diff + "```"]
    if stage == "candidate":
        parts += ["## 原生读写调用（仅投影调用名、参数与成功状态）",
                  "```json\n" + json.dumps(selected["revision_calls"], ensure_ascii=False, indent=2) + "\n```"]
    if stage == "revision":
        parts += ["这次补丁由审阅代理编写，后续任务由在线模型执行；不是模型自主纠错。"]
    tasks = ["investigation"] if stage == "origin" else ["west", "single"]
    for name in tasks:
        task = selected[name]
        metadata = {k: task[k] for k in ("method_sha256", "history_at_start", "loaded_method", "checks")}
        parts += [f"## {name}：实际工具回执",
                  "```json\n" + json.dumps(metadata, ensure_ascii=False, indent=2) + "\n```",
                  "```json\n" + json.dumps(task["queries"], ensure_ascii=False, indent=2) + "\n```",
                  "### 原回答（保留原文，可能有误）", task["final_response"]]
    parts += ["这些是已保存版本的观察，不是你修改后的新运行；结构检查不覆盖全文语义。"
              "没有原版在同一 west 现场的配对，不能据此断言新版全面更好。"]
    return "\n\n".join(parts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("origin", "candidate", "revision"), default="origin")
    print(render(parser.parse_args().stage))
