"""CO2e estimation from token counts.

Every figure is an ARITHMETIC ESTIMATE, not a measurement:

    grams CO2e = tokens x wh_per_token / 1000 x grid_g_per_kwh

Both factors are assumptions you can override on the command line. The
defaults (0.0045 Wh/token, 400 g CO2e/kWh) multiply to the 0.0018 g/token
this project has always used. They are illustrative, not sourced: published
per-prompt figures differ by more than 10x between studies, so treat
output as a way to compare reply lengths, never as carbon accounting.

The "standard" (verbose) baseline is either:
  - assumed: concise tokens x a per-mode multiplier (3.4 / 2.6 / 1.9). With
    this baseline the saved percentage depends only on the mode, not on the
    content, so it demonstrates the arithmetic and proves nothing; or
  - measured: pass baseline_tokens from a real unconstrained completion.
"""

WH_PER_TOKEN = 0.0045
GRID_G_PER_KWH = 400.0
CO2_PER_TOKEN_G = round(WH_PER_TOKEN / 1000 * GRID_G_PER_KWH, 10)  # 0.0018
VERBOSE_MULTIPLIER = {"sprout": 3.4, "canopy": 2.6, "full": 1.9}


def footprint(out_tokens, mode, *, baseline_tokens=None,
              wh_per_token=WH_PER_TOKEN, grid_g_per_kwh=GRID_G_PER_KWH):
    """Compare a concise reply against a verbose baseline."""
    if mode not in VERBOSE_MULTIPLIER:
        raise ValueError(
            f"unknown mode {mode!r}; expected one of {sorted(VERBOSE_MULTIPLIER)}"
        )
    if wh_per_token <= 0 or grid_g_per_kwh <= 0:
        raise ValueError("wh_per_token and grid_g_per_kwh must be positive")
    if baseline_tokens is None:
        std_tokens = round(out_tokens * VERBOSE_MULTIPLIER[mode])
        baseline_kind = "assumed"
    else:
        std_tokens = max(0, int(baseline_tokens))
        baseline_kind = "measured"
    g_per_token = wh_per_token / 1000 * grid_g_per_kwh
    eco_co2 = out_tokens * g_per_token
    std_co2 = std_tokens * g_per_token
    saved_pct = max(0, round((1 - out_tokens / std_tokens) * 100)) if std_tokens else 0
    return {
        "eco_tokens": out_tokens,
        "standard_tokens": std_tokens,
        "eco_co2_g": round(eco_co2, 4),
        "standard_co2_g": round(std_co2, 4),
        "saved_pct": saved_pct,
        "saved_co2_g": round(max(0.0, std_co2 - eco_co2), 4),
        "baseline_kind": baseline_kind,
        "wh_per_token": wh_per_token,
        "grid_g_per_kwh": grid_g_per_kwh,
    }
