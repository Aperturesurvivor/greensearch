# Audit — 2026-10-27 (work for 0.7.0, not yet pushed)

Scope: the v0.6.0 working tree in this folder, plus the website demo.
Method: full test run, grep for authorship references and secrets,
manual read of providers / CLI / session / shrink / footprint, and
re-running the corpus numbers. No live model was available (no
GREENSEARCH_API_KEY in the environment), so live-provider code paths
were reviewed and unit-tested with fakes, not exercised against a
real endpoint.

## Findings fixed in 0.7.0

- Website loaded Google Fonts externally while its README said
  "nothing leaves the page". Fixed: the font links were removed and
  the CSS now uses system fonts only. Appearance falls back to the
  system sans/mono stack; no font files were added.
- CHANGELOG said the corpus input saving was 30%; the corpus test
  actually reports 80 of 247 tokens, 32%. Fixed to 32%.
- README said 71 tests and that PromptShrink was "not yet" in the
  harness. Both were stale after 0.6.0. Fixed: 89 tests, PromptShrink
  listed as present since 0.6.0, session cache listed as present
  since 0.7.0.
- CLI had a redundant ternary for the measured baseline
  (`provider.complete_ex(prompt) if live else provider.complete_ex(prompt)`).
  Removed; behaviour unchanged.
- No Claude, Muse, Anthropic, or AI-authorship references were found
  in any tracked file, and the local git log's only author is Grant
  O'Brien. Nothing had to be removed from the repo for that item.
  Note: the expanded-library patch in ~/workspace/user/files/ (outside
  this repo) still carries a Claude patch header; if that patch is
  ever applied, strip its header before pushing.

## Findings noted, not changed

- Mode naming is still split: Forest on the site, Full in the harness.
  Documented in the README; renaming would touch the site, router,
  tests, and routing spec, and was left for a dedicated change.
- Local git state is messy and predates this work: the local repo's
  only commit is v0.4.0, the v0.6.0 changes are uncommitted, and no
  remote is configured locally. GitHub's head (via the snapshot-push
  record) is v0.6.0. This work was deliberately left uncommitted and
  unpushed, pending approval, so nothing here overwrites that head.
- PromptShrink's filler list can change meaning in edge cases (e.g.
  removing a lone "also"). This is a known heuristic trade-off, not a
  bug found by a test, and was not changed.
- Session files store prompts and answers in plain text. Documented
  in the README; users should not put secrets in prompts.
- No secrets, keys, or tokens were found in the repo files.

## Live-model coverage gap

- Baseline study: canned only (see BASELINE.md). The live study
  script exits 2 without a key and writes nothing.
- Cascade: logprob parsing is implemented against the
  OpenAI-compatible chat-completions shape and tested with fakes.
  It has not been run against a real endpoint, because no key was
  available. The first live cascade run should be checked before
  any claim about escalation rates is made.
- Tokenizer: tiktoken was verified in a clean venv (see CHANGELOG),
  but the default system Python does not have it installed, so the
  tiktoken unit tests skip there by design.

## Open items after 0.7.0

- Apply or reject the expanded 89-topic library patch (audited
  separately; not part of this work).
- Run the live baseline study and the first live cascade run once a
  key is available, and record the results in BASELINE.md.
- Decide on the Forest/Full rename, and on a PyPI publish.
