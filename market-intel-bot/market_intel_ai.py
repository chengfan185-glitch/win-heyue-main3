# market_intel_ai.py
"""
Market Intel AI Layer
---------------------
- 接收量化初筛后的市场快照
- 调用 OpenAI / Grok（xAI）
- 输出结构化市场判断 JSON
"""

import os
import json
import time
from typing import Dict, Any, List, Literal
from datetime import datetime

# ========== Model Switch ==========
AI_PROVIDER: Literal["openai", "grok"] = os.getenv("MARKET_INTEL_PROVIDER", "openai")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
XAI_API_KEY = os.getenv("XAI_API_KEY", "")

# ========== Prompt ==========
BASE_PROMPT = """
你是一个加密货币市场结构分析助手。
你的任务不是给出买卖建议，而是分析市场结构。

基于我提供的数据，请输出：
1. 当前市场状态（trend / weak_trend / range / risk_off）
2. 强势板块（如有）
3. 强势币 TopN（最多 10 个）
4. 明显弱势或高风险币清单

要求：
- 不给具体买卖点
- 不预测价格
- 不涉及杠杆或仓位
- 只基于输入数据判断
- 严格输出 JSON
"""

# ========== Provider Clients ==========
def call_openai(payload: Dict[str, Any]) -> Dict[str, Any]:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    resp = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": BASE_PROMPT},
            {"role": "user", "content": json.dumps(payload)}
        ],
        temperature=0.2
    )
    return json.loads(resp.choices[0].message.content)


def call_grok(payload: Dict[str, Any]) -> Dict[str, Any]:
    import requests

    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "grok-2",
        "messages": [
            {"role": "system", "content": BASE_PROMPT},
            {"role": "user", "content": json.dumps(payload)}
        ],
        "temperature": 0.3
    }

    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])


# ========== Main Entry ==========
def run_market_intel(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    主入口：供 market-intel-bot / scheduler 调用
    """
    if AI_PROVIDER == "openai":
        result = call_openai(snapshot)
        model_used = "openai"
    elif AI_PROVIDER == "grok":
        result = call_grok(snapshot)
        model_used = "grok"
    else:
        raise ValueError(f"Unknown AI provider: {AI_PROVIDER}")

    result["meta"] = {
        "model": model_used,
        "generated_at": datetime.utcnow().isoformat() + "Z"
    }
    return result


# ========== CLI Test ==========
if __name__ == "__main__":
    test_snapshot = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "market_overview": {
            "btc_trend": "up",
            "eth_trend": "sideways",
            "advancers_ratio": 0.61,
            "avg_volatility": 0.017
        },
        "candidates": []
    }

    output = run_market_intel(test_snapshot)
    print(json.dumps(output, indent=2, ensure_ascii=False))
