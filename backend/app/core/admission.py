from starlette.responses import JSONResponse


class InferenceAdmissionMiddleware:
    """Hold capacity for the entire response, including streaming and cancellation."""

    def __init__(self, app, state):
        self.app, self.state = app, state

    async def __call__(self, scope, receive, send):
        heavy = (
            scope["type"] == "http"
            and scope.get("method") == "POST"
            and (
                scope["path"] == "/api/translate"
                or scope["path"].startswith("/api/speech/")
            )
        )
        if not heavy:
            return await self.app(scope, receive, send)
        if self.state.in_flight >= 4:
            return await JSONResponse(
                {"detail": "AI workers are busy. Please retry shortly."},
                status_code=429,
                headers={"Retry-After": "5"},
            )(scope, receive, send)
        self.state.in_flight += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.state.in_flight -= 1
