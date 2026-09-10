"""Los modelos Pydantic de entrada y salida.

**Los schemas de respuesta listan los campos uno por uno.** Nunca se serializa un modelo ORM
entero: es lo que garantiza que `trust_score`, `session_token_hash`, `fingerprint_hash`,
`is_honeypot` y `expected_answer` no salgan jamás de la API (`docs/12-api.md` §1.4, RF-207).
Ver ADR-015.
"""
