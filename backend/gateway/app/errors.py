class ServiceError(Exception):
    """Raised by service functions to produce a {"error": message} JSON response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
