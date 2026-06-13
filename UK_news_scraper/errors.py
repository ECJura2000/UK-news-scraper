class UKNewsError(Exception):
    retryable = False


class DownloadError(UKNewsError):
    retryable = True


class ParseError(UKNewsError):
    pass


class ValidationError(UKNewsError):
    pass


class StorageError(UKNewsError):
    pass


def is_retryable_error(error: BaseException) -> bool:
    return bool(getattr(error, "retryable", False))
