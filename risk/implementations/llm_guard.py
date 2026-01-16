# risk/implementations/llm_guard.py

from typing import Dict, Any
import json
import time

from risk.interfaces.risk_review import RiskReviewer, RiskReviewResult


class LLMGuard(RiskReviewer):
    """
    LLM-based risk reviewer.
    Acts as a veto gate, not a signal generator.
    """

    name = "llm_guard"

    def __init__(
        self,
        llm_client,
        model: str,
        timeout_sec: int = 5,
        temperature: float = 0.1,
    ):
        self.llm_client = llm_client
        self.model = model
        self.timeout_sec = timeout_sec
        self.temperature = temperature

    def review(self, payload: Dict[str, Any]) -> RiskReviewResult:
        system_prompt = """
You are a Strategy Co-Pilot for a quantitative trading system.

Your role is strictly limited to reviewing whether a proposed trade
is consistent with the current market state and risk constraints.

You must NOT:
- Predict price movement
- Output BUY, SELL, LONG, or SHORT
- Suggest position sizing
- Encourage trading

You must:
- Evaluate alignment between strategy intent and market context
- Identify high-noise or low-confidence situations
- Decide whether to ALLOW, BLOCK, or CAUTION the trade
- Provide concise, explainable reasons

Default behavior:
If uncertainty is high, prefer BLOCK or CAUTION.
Preservation of capital has priority over opportunity.
"""

        user_prompt = f"""
Review the following proposed trade from a quantitative system.

Assess whether the trade should be allowed to proceed
based on market state consistency and risk discipline.

Return your answer strictly in the specified JSON format.
Do not include any extra commentary.

{json.dumps(payload, ensure_ascii=False)}
"""

        try:
            resp = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                timeout=self.timeout_sec,
            )

            raw = resp.choices[0].message.content
            result = json.loads(raw)

            decision = result.get("decision")

            if decision not in ("ALLOW", "BLOCK", "CAUTION"):
                raise ValueError("Invalid decision from LLM")

            return {
                "decision": decision,
                "reason": result.get("reason", []),
                "risk_tags": result.get("risk_tags", []),
                "confidence": float(result.get("confidence_in_advice", 0.0)),
                "reviewer": self.name,
                "ts": time.time(),
            }

        except Exception as e:
            # LLM 异常：强制 BLOCK
            return self._block(
                reason=["LLM failure or invalid response"],
                risk_tags=["llm_error"],
                confidence=1.0,
            )
