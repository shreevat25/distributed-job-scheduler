"""Worker runtime: long-running processes that drive jobs through their lifecycle.

- ``runner``    — WorkerRunner: poll/claim loop composing the pieces below
- ``executor``  — runs one claimed job (start, handler, complete/fail, lease renewal)
- ``heartbeat`` — worker registration, status, and liveness heartbeats
- ``shutdown``  — draining, signal handling, and bounded task drain
- ``reaper``    — recovery loop (stale workers, expired leases)
- ``scheduler`` — promotion loop (delayed/retry jobs, cron materialization)
- ``handlers``  — registry of safe, deterministic job handlers
"""
