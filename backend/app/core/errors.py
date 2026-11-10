class ServiceError(Exception):
    def __init__(self, message: str, status: int = 503):
        self.message = message
        self.status = status
