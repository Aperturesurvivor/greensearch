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

# Per-model-size energy factors (Wh/token), shown as ranges.
# Sources:
#   - Luccioni et al. 2023, "Power Hungry Processing" (ACL 2024):
#     measured inference energy for models from 0.5B to 176B parameters.
#   - de Vries 2023, "The growing energy footprint of AI" (Joule):
#     estimated 0.001-0.01 Wh per query for smaller models, 0.01-0.03+
#     for larger (70B+).
#   - IEA 2024, "Electricity 2024" report: 2.9 Wh per ChatGPT query
#     (GPT-4-class, ~1.8T params), approximately 0.003-0.006 Wh/token
#     at typical query lengths.
# These are ORDER-OF-MAGNITUDE estimates. Real values depend on hardware,
# batch size, quantisation, and serving stack, none of which OpenRouter
# discloses. Treat as illustrative context, not accounting.
WH_PER_TOKEN_RANGES = {
    # (min Wh/token, max Wh/token, label)
    "small":  (0.0005, 0.002,  "< 10B params"),
    "medium": (0.002,  0.006,  "10B - 70B params"),
    "large":  (0.004,  0.015,  "> 70B params"),
}

# Cooling water use effectiveness, litres per kWh, for modern closed-loop
# systems. Shown as a range, never a single number: older evaporative
# systems are 1.7-2.5 L/kWh, and electricity-generation water (about
# 4.52 L/kWh in most models) is excluded here, so the water figures are
# cooling water only, not total water.
WUE_L_PER_KWH_LOW = 0.1
WUE_L_PER_KWH_HIGH = 0.3


def model_size_tier(model_name):
    """Guess model size tier from model name. Returns 'small', 'medium',
    or 'large'. Falls back to 'medium' if unclear."""
    if not model_name:
        return "medium"
    name = model_name.lower()
    # Look for parameter counts in model names
    import re
    m = re.search(r'(\d+\.?\d*)\s*[bB]', name)
    if m:
        params_b = float(m.group(1))
        if params_b < 10:
            return "small"
        elif params_b <= 70:
            return "medium"
        else:
            return "large"
    # Name-based heuristics
    for tag in ("mini", "tiny", "nano", "1b", "3b", "7b", "8b"):
        if tag in name:
            return "small"
    for tag in ("70b", "72b", "405b", "gpt-4", "opus", "sonnet"):
        if tag in name:
            return "large"
    return "medium"


def energy_receipt(input_tokens, output_tokens, *, model=None,
                   model_tier=None, escalated=False, cache_hit=False,
                   wh_per_token=WH_PER_TOKEN, grid_g_per_kwh=GRID_G_PER_KWH,
                   wue_low=WUE_L_PER_KWH_LOW, wue_high=WUE_L_PER_KWH_HIGH):
    """Per-answer energy receipt: an arithmetic estimate, never accounting.

    Returns a dict the server puts in meta["energy"] and the site can
    render as a receipt. When the provider did not report token usage,
    status is "unavailable" and no number is invented: energy, CO2e and
    water are all None, with the reason stated. A cache hit is 0 tokens,
    so it is 0 Wh / 0 g / 0 mL, with a note saying why.

    Water is cooling water only: energy_wh * WUE, in millilitres
    (Wh / 1000 = kWh, x L/kWh = litres, x 1000 = mL, so mL = Wh x WUE).
    Electricity-generation water is excluded and the note says so.
    Grid intensity is the configured factor, not a measured location:
    OpenRouter does not disclose where inference ran, so no region
    (Finland or otherwise) is claimed for the receipt.
    """
    size_tier = model_size_tier(model)
    size_range = WH_PER_TOKEN_RANGES.get(size_tier, WH_PER_TOKEN_RANGES["medium"])
    base = {
        "basis": "estimate",
        "model": model,
        "model_tier": model_tier,
        "model_size_tier": size_tier,
        "escalated": escalated,
        "cache_hit": cache_hit,
        "factors": {
            "wh_per_token": wh_per_token,
            "wh_per_token_range": [size_range[0], size_range[1]],
            "wh_per_token_range_label": size_range[2],
            "grid_g_per_kwh": grid_g_per_kwh,
            "grid_region": "unknown",
            "wue_l_per_kwh_low": wue_low,
            "wue_l_per_kwh_high": wue_high,
        },
    }
    if input_tokens is None or output_tokens is None:
        return {
            **base,
            "status": "unavailable",
            "reason": ("Provider did not report token usage, so no energy "
                       "estimate was made."),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": None,
            "energy_wh": None,
            "co2e_g": None,
            "water_ml_low": None,
            "water_ml_high": None,
            "note": None,
        }
    if wh_per_token <= 0 or grid_g_per_kwh <= 0 or wue_low <= 0 or wue_high <= 0:
        raise ValueError("energy factors must be positive")
    total = int(input_tokens) + int(output_tokens)
    wh = total * wh_per_token
    note = ("Arithmetic estimate from provider-reported tokens, not a "
            "measurement and not carbon accounting. Inference region "
            "unknown (provider does not disclose it), so the grid "
            "factor is illustrative. Water is cooling water only; "
            "electricity-generation water is excluded.")
    if cache_hit:
        note = ("Cache hit: no new model call, so this answer cost no new "
                "tokens or energy. " + note)
    if escalated:
        note = ("Total covers the primary call and the escalation call. " + note)
    return {
        **base,
        "status": "estimate",
        "reason": None,
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": total,
        "energy_wh": round(wh, 4),
        "co2e_g": round(wh / 1000 * grid_g_per_kwh, 4),
        "water_ml_low": round(wh * wue_low, 4),
        "water_ml_high": round(wh * wue_high, 4),
        "note": note,
    }
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
