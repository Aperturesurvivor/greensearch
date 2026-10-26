"""CO2e estimation from token counts.

All figures here are ARITHMETIC ESTIMATES, not measurements:
  grams CO2e = tokens * 0.0018
The "standard reply" token count is the concise reply's tokens times a
per-mode multiplier (sprout 3.4, canopy 2.6, full 1.9), encoding the
assumption that a typical verbose reply uses that many times the tokens.
Treat the output as an illustration for comparing reply lengths, never
as carbon accounting.
"""

CO2_PER_TOKEN_G = 0.0018
VERBOSE_MULTIPLIER = {"sprout": 3.4, "canopy": 2.6, "full": 1.9}


def footprint(out_tokens, mode):
    """Compare a concise reply against an estimated verbose baseline."""
    if mode not in VERBOSE_MULTIPLIER:
        raise ValueError(
            f"unknown mode {mode!r}; expected one of {sorted(VERBOSE_MULTIPLIER)}"
        )
    std_tokens = round(out_tokens * VERBOSE_MULTIPLIER[mode])
    eco_co2 = out_tokens * CO2_PER_TOKEN_G
    std_co2 = std_tokens * CO2_PER_TOKEN_G
    saved_pct = max(0, round((1 - out_tokens / std_tokens) * 100)) if std_tokens else 0
    return {
        "eco_tokens": out_tokens,
        "standard_tokens": std_tokens,
        "eco_co2_g": round(eco_co2, 2),
        "standard_co2_g": round(std_co2, 2),
        "saved_pct": saved_pct,
        "saved_co2_g": round(std_co2 - eco_co2, 2),
    }
