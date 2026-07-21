# Explicit defaults and optional evaluation

Pipeline defaults live in `constants.py` and meaningful detection controls are
CLI arguments. Runtime files share one `--data-dir`; components do not maintain
independent path configuration.

Ragas/OpenAI are optional evaluation dependencies. Core download, detection,
retrieval, classification, and reporting installs do not pull the evaluation
stack.

Dormant Langfuse tracing and its Docker services were removed. Ragas Faithfulness
and tracked JSON outputs provide the rationale check needed for this historical
showcase.