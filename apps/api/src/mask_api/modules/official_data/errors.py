class OfficialDataError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("official source response could not be normalized safely")
