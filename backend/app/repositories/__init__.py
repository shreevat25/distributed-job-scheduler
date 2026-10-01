"""Repository layer — the only package that issues SQL.

Repositories expose persistence primitives (queries, row locks, inserts and
DB-clock expressions). They never commit; transaction boundaries belong to
the calling service or worker loop.
"""
