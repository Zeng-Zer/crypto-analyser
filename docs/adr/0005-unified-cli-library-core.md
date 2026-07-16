# One CLI over a library core

The project exposes one installed command, `crypto-analyser`, through these workflows:

- `run`
- `news init`
- `news load`
- `news embed`
- `news search`
- `evaluate`

Domain modules do not parse arguments, exit processes, or invoke sibling
modules through subprocesses. `pipeline.py` composes Python functions directly;
`cli.py` is the only argument-parsing boundary.

This keeps component behavior unit-testable while preserving a polished demo
surface. Operational news setup remains discoverable without restoring one
script per pipeline stage.