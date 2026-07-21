# Severity is derived from detection strength, not LLM-emitted

`severity` measures price deviation, not model judgment. Detection assigns it
from the strongest normalized price-Z, 4-hour-drawdown, or 2-hour-return trigger:

- `low`: ≥1.0× threshold
- `medium`: ≥1.2× threshold
- `high`: ≥1.6× threshold
- `extreme`: ≥2.0× threshold

Classification copies this value from the episode record. The LLM emits only
classification, confidence, concise synthesis, detailed rationale, and event reference.
This keeps repeated ablation runs from changing an objective market feature.

The current LUNA run contains eight episodes. Severity uses the strongest normalized price-Z, 4-hour-drawdown, or 2-hour-return trigger; the raw-price peak remains |Z| 4.31 (`high`).
See `CONTEXT.md` for domain terminology and the packaged classification schema
for the LLM output contract.