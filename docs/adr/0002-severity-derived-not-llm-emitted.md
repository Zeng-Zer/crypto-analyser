# Severity is derived from peak |Z|, not LLM-emitted

`severity` measures price deviation, not model judgment. Detection assigns it
from episode peak |Z| using the shared vocabulary:

- `low`: ≥2.5
- `medium`: ≥3.0
- `high`: ≥4.0
- `extreme`: ≥5.0

Classification copies this value from the episode record. The LLM emits only
classification, confidence, rationale, news relevance, and event reference.
This keeps repeated ablation runs from changing an objective market feature.

The current LUNA run contains five episodes and reaches peak |Z| 4.31 (`high`).
See `CONTEXT.md` for domain terminology and the packaged classification schema
for the LLM output contract.