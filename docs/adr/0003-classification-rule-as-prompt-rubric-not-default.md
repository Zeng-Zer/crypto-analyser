# Classification rule is a prompt rubric, not a deterministic default

The LLM applies the derivatives threshold rule itself. Orchestration passes raw
funding and open-interest features plus configured thresholds; it does not
precompute a verdict for the model to accept or override.

The rubric comes from explicit constants passed into prompt construction:

- `|funding rate| >= 0.0500%`, or
- `|4h open-interest change| >= 10%`

A deterministic default made rationales post-hoc explanations of an answer the
model was already given. Letting the model apply the visible rubric keeps the
rationale substantive and lets it handle missing data and news relevance.

Trade-off: model upgrades can change a verdict for identical inputs. That is
acceptable for this qualitative LLM evaluation, and tracked outputs preserve
exact observed runs. Direct verdict change remains the primary controlled-comparison result;
Ragas Faithfulness checks combined-output rationale support.