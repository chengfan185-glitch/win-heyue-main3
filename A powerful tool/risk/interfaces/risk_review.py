# risk/interfaces/risk_review.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List, TypedDict
import time


class RiskReviewResult(TypedDict):
    """
    Standardized risk review output.
    All risk reviewers MUST return this structure.
    """
    decision: str                  # ALLOW | BLOCK | CAUTION
    reason: List[str]               # human-readable explanations
    risk_tags: List[str]            # machine-usable tags
    confidence: float               # confidence in this review (0.0 - 1.0)
    reviewer: str                   # identifier of reviewer
    ts: float                       # unix timestamp


class RiskReviewer(ABC):
    """
    Abstract base class for all risk reviewers.
    A risk reviewer has veto power but no execution power.
    """

    name: str = "unknown_reviewer"

    @abstractmethod
    def review(
        self,
        payload: Dict[str, Any]
    ) -> RiskReviewResult:
        """
        Review a proposed trade and decide whether it should proceed.

        Parameters
        ----------
        payload : Dict[str, Any]
            A structured description of the proposed trade,
            market context, and risk constraints.

        Returns
        -------
        RiskReviewResult
            Standardized decision result.
        """
        raise NotImplementedError

    def _block(
        self,
        reason: List[str],
        risk_tags: List[str],
        confidence: float = 1.0
    ) -> RiskReviewResult:
        return {
            "decision": "BLOCK",
            "reason": reason,
            "risk_tags": risk_tags,
            "confidence": confidence,
            "reviewer": self.name,
            "ts": time.time(),
        }

    def _allow(
        self,
        reason: List[str],
        risk_tags: List[str] = None,
        confidence: float = 1.0
    ) -> RiskReviewResult:
        return {
            "decision": "ALLOW",
            "reason": reason,
            "risk_tags": risk_tags or [],
            "confidence": confidence,
            "reviewer": self.name,
            "ts": time.time(),
        }

    def _caution(
        self,
        reason: List[str],
        risk_tags: List[str],
        confidence: float = 0.5
    ) -> RiskReviewResult:
        return {
            "decision": "CAUTION",
            "reason": reason,
            "risk_tags": risk_tags,
            "confidence": confidence,
            "reviewer": self.name,
            "ts": time.time(),
        }
