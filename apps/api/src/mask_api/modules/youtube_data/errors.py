class YouTubeDataError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("YouTube response could not be normalized safely")
