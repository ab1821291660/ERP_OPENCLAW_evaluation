"""
LLM-as-judge rubric evaluator — uses an LLM to score response quality.
Judge prompt is in Chinese for the customer_support domain.   ##customer_support ##===================================
"""
import json
JUDGE_PROMPT = """你是一个评测裁判。请根据以下标准对候选回答进行评分：

标准：
1. 相关性：回答是否直接回应了用户问题？（0-1分）
2. 完整性：回答是否包含了所有必要信息？（0-1分）
3. 准确性：回答内容是否准确、无幻觉？（0-1分）

用户问题：{question}
期望包含的关键信息：{must_include}
候选回答：{candidate_answer}

请以 JSON 格式返回：{{"relevance": 0.0, "completeness": 0.0, "accuracy": 0.0, "overall": 0.0, "reasoning": "..."}}"""


async def evaluate(candidate_output: dict, expected: dict) -> dict:
    question = candidate_output.get("_question", "")
    answer = candidate_output.get("answer", str(candidate_output))
    must_include = expected.get("must_include", [])
    prompt = JUDGE_PROMPT.format(
        question=question,
        must_include=", ".join(must_include),
        candidate_answer=str(answer)[:2000],
    )


    from app.runtime_config import get_llm_api_key, get_llm_base_url, get_llm_model
    api_key = get_llm_api_key()
    base_url = get_llm_base_url() or "https://api.deepseek.com"
    model = get_llm_model()
    if not api_key:
        return {"score": 0.5, "evaluator": "rubric_judge", "passed": False, "detail": {"reason": "No LLM available for judging"}}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url=f"{base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                },
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        return {"score": 0.5, "evaluator": "rubric_judge", "passed": False, "detail": {"reason": str(exc)}}


    try:
        raw = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        scores = json.loads(raw)
    except json.JSONDecodeError:
        scores = {"overall": 0.5, "reasoning": "Failed to parse judge output"}
    overall = scores.get("overall", 0.5)##===================================
    return {
        "score": round(overall, 3),
        "evaluator": "rubric_judge",
        "passed": overall >= 0.6,
        "detail": scores,
    }
