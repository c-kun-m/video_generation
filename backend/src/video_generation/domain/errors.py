from video_generation.contracts.models import ErrorDetail


class DomainError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        current_row_version: int | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.detail = ErrorDetail(
            code=code, message=message, current_row_version=current_row_version
        )


def not_found() -> DomainError:
    return DomainError("NOT_FOUND", "项目或记录不存在，或当前身份无权访问。", 404)
