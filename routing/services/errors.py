class RoutingError(Exception):
    """An error that maps directly to an HTTP status and a JSON message."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status
