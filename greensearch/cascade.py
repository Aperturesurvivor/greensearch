"""Confidence-gated cascade, done properly.

Rules, stated up front so they can be checked:
  1. The only confidence signal is the primary model's own token
     logprobs (mean logprob of the generated tokens). No signal is
     ever invented from answer length, word count, or any other proxy.
  2. If logprobs are unavailable (demo provider, or an endpoint that
     does not report them), the cascade does NOT escalate and does NOT
     claim confidence. It returns the primary answer with
     escalated=False and reason="logprobs unavailable".
  3. If mean logprob >= threshold, the primary answer stands.
  4. If mean logprob < threshold, the escalation model is called with
     the same system prompt and token cap, and its answer replaces the
     primary one. An escalation failure is raised, not silently
     downgraded to the low-confidence primary answer.
  5. A judge-model cascade is NOT implemented here. That would need a
     second model call with a judge prompt and a threshold for the
     judge's score, which is a separate, more expensive design.

Threshold: --cascade-threshold, default -1.0 (mean token probability
about e^-1.0, roughly 37%). This is a starting point to tune against
real runs, not a sourced constant; BASELINE.md is where tuned values
should be recorded with their data.
"""

from dataclasses import dataclass

from greensearch.providers import ProviderError


@dataclass
class CascadeResult:
    completion: object  # greensearch.providers.Completion
    escalated: bool
    avg_logprob: object  # float or None
    reason: str
    primary_model: str
    escalation_model: str = ""


def run_cascade(primary, escalation, prompt, system=None, max_tokens=None, threshold=-1.0):
    """Run primary, escalate on low mean logprob, return a CascadeResult."""
    if threshold > 0:
        raise ValueError("cascade threshold must be <= 0 (logprobs are negative or zero)")
    primary_comp = primary.complete_ex(
        prompt, system=system, max_tokens=max_tokens, logprobs=True
    )
    avg = primary_comp.avg_logprob
    primary_name = getattr(primary, "model", getattr(primary, "name", "primary"))
    escalation_name = getattr(escalation, "model", getattr(escalation, "name", "escalation"))
    if avg is None:
        return CascadeResult(
            completion=primary_comp, escalated=False, avg_logprob=None,
            reason="logprobs unavailable: no escalation, primary answer stands",
            primary_model=primary_name, escalation_model=escalation_name,
        )
    if avg >= threshold:
        return CascadeResult(
            completion=primary_comp, escalated=False, avg_logprob=avg,
            reason=f"mean logprob {avg:.3f} >= threshold {threshold}",
            primary_model=primary_name, escalation_model=escalation_name,
        )
    # Low confidence: escalate. A failure here propagates (ProviderError
    # or ValueError) rather than silently returning the primary answer.
    esc_comp = escalation.complete_ex(prompt, system=system, max_tokens=max_tokens)
    return CascadeResult(
        completion=esc_comp, escalated=True, avg_logprob=avg,
        reason=f"mean logprob {avg:.3f} < threshold {threshold}: escalated",
        primary_model=primary_name, escalation_model=escalation_name,
    )
