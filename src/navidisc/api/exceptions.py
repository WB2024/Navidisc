"""Subsonic API exceptions."""


class SubsonicError(Exception):
    """Base exception for Subsonic API errors."""
    
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message


class AuthenticationError(SubsonicError):
    """Authentication failed."""
    pass


class PlaylistNotFoundError(SubsonicError):
    """Requested playlist was not found."""
    
    def __init__(self, identifier: str):
        super().__init__(f"Playlist not found: {identifier}")
        self.identifier = identifier


class ConnectionError(SubsonicError):
    """Could not connect to server."""
    pass


class APIError(SubsonicError):
    """Generic API error with error code from server."""
    
    # Subsonic error codes
    ERROR_CODES = {
        0: "Generic error",
        10: "Required parameter is missing",
        20: "Incompatible Subsonic REST protocol version",
        30: "Incompatible Subsonic REST protocol version (server)",
        40: "Wrong username or password",
        41: "Token authentication not supported",
        50: "User is not authorized for the given operation",
        60: "Trial period is over",
        70: "Requested data was not found",
    }
    
    def __init__(self, message: str, code: int):
        description = self.ERROR_CODES.get(code, "Unknown error")
        super().__init__(f"{message}: {description}", code)
