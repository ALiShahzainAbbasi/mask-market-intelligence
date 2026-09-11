class OnetDataError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("O*NET database content could not be normalized safely")
