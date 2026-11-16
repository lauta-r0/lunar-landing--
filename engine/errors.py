# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Engine error type shared with the API layer (CONTRACT section 5)."""


class EngineError(Exception):
    """Expected, user-facing failure of the engine.

    code:    machine-readable id, e.g. "out_of_coverage", "out_of_ephemeris_range", "bad_request"
    message: human-readable English sentence
    extra:   optional dict merged into the API error body (e.g. {"suggested_target": {...}})
    """

    def __init__(self, code: str, message: str, extra: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra or {}

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message, **self.extra}
