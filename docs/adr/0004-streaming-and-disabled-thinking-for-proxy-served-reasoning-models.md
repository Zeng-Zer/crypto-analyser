# Streaming and disabled thinking for proxy-served reasoning models

`LLMClient.classify()` calls the LLM with `stream: True` and
`chat_template_kwargs: {"enable_thinking": False}` in the request payload. Both
flags are retained for the current model (`glm-5.2-short`, served through a
proxy) and were added after the synchronous non-streaming path failed
during classifier integration testing.

Streaming remains required because this proxy serving path rejects the
non-streaming request path: a plain `POST /chat/completions` without
`stream: True` returns HTTP 500, and even when it returns 200 it tends to hold
the connection open longer than the client read-timeout (`requests` `timeout=120`
is the interval between bytes), producing an apparent hang mid-pipeline. With
`stream: True` we get incremental SSE chunks (`choices[0].delta.content`) and
the connection stays supplied with bytes while the model generates, so the
read-timeout is never tripped by a slow-but-alive generation. The client
accumulates the chunks into one string and `json.loads`-es it exactly as the
non-streaming path would have done — there is no UI, the user-visible latency
is the same (we wait for the full output anyway), and streaming was not added
for token-by-token rendering. It was added because the model does not otherwise
return.

Disabling thinking (`enable_thinking: False`) is required because the model's
default behavior emits chain-of-thought tokens before the structured JSON
answer. With thinking on, ep6 during QA blew the 120s read-timeout budget on
reasoning tokens before the JSON was emitted, surfacing as the same hang as
above for a different reason. The classifier's job is to produce a single
structured JSON object (`response_format` strict-mode
the packaged classification schema); chain-of-thought is never read, never stored,
never scored — it is pure budget burn. Disabling it makes the model emit the
JSON directly, which is what the pipeline consumes.

The flags carry an implicit assumption about the model serving path. If a
future model is served directly (no proxy, real OpenAI-compatible / a model
that genuinely supports non-streaming batch), `stream: True` could be dropped
and the simpler `resp.json()` path restored — but only after confirming the
non-streaming path actually returns within the timeout budget for this model.
If a future task genuinely needs reasoning tokens (e.g. Milestone 2 debate layer
where Bull/Bear/Judge agents want visible reasoning for the showcase), the
right move is not to flip `enable_thinking: True` on this single classify call
but to introduce a dedicated streaming-with-thinking client that surfaces the
reasoning separately, raises `max_tokens` to accommodate the reasoning budget,
and raises `timeout` to match. Mixing thinking + strict-mode JSON in one call is
fragile: the model can spend the token budget on reasoning and truncate the
JSON, which `from_dict` then rejects with `ClassificationValidationError`.

Hard to reverse: any caller relying on incremental SSE chunks (the unpacker is
in `LLMClient.classify`) and the assumption that this specific model needs the
two flags to return at all. Surprising without context: a reader sees
`enable_thinking: False` and assumes we are handicapping the model for cost or
speed; in fact it is correctness — without the flag, the classification call
times out. Real trade-off: model-capability suppression vs. the pipeline
actually completing; given that the classifier only consumes the structured
JSON object, nothing is lost by suppressing thinking on this call.