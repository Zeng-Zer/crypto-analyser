# Streaming and forced tool output for reasoning models

`LLMClient.classify()` uses the OpenAI-compatible Chat Completions endpoint with
`stream: true`, `reasoning_effort: medium`, and one forced
`emit_classification` tool. Classifier and Ragas judge calls use the same medium
reasoning effort.

Streaming remains required because the proxy path can hold a non-streaming
connection longer than the client read timeout. Incremental SSE chunks keep the
connection active while the model reasons. The classifier collects only forced
tool argument fragments and validates the completed object against application
types before storing it.

The previous GLM configuration used
`chat_template_kwargs: {"enable_thinking": false}` and strict
`response_format`. That combination was removed for `gpt-5.6-luna`. Luna
supports explicit reasoning effort, but its Plexus Chat Completions route did
not reliably enforce the complex classification schema through
`response_format`. A forced tool call on the same endpoint returned the full
schema correctly in deployment probes.

Medium reasoning balances classifier quality, latency, and token use. The
8,000-token ceiling includes private reasoning tokens and final tool arguments.
Reasoning text is not exposed, persisted, or rendered.

Hard to reverse: callers depend on streamed tool argument assembly and Plexus's
top-level tool choice shape, `{ "type": "function", "name": "emit_classification" }`.
Any model or gateway change must pass a full-schema streamed probe before
deployment.
