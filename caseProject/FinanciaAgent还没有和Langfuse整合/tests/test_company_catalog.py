from app.agent_factory import build_model
from app.tools import retrieval


def test_company_lookup():
    results = retrieval.search_financial_reports.invoke(
        {"query": "Apple 2014 long-term debt"}
    )
    assert results, "真实 agent.db 中没有找到候选报告"
    print([item["report_id"] for item in results])


def test_model():
    llm = build_model()
    resp = llm.invoke('用三句话简单介绍一下：机器学习的基本概念')
    print(resp)

if __name__ == "__main__":
    # test_company_lookup()
    test_model()