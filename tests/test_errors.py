from UK_news_scraper.errors import DownloadError, ParseError, StorageError, ValidationError, is_retryable_error


def test_only_download_errors_are_retryable():
    assert is_retryable_error(DownloadError("temporary"))
    assert not is_retryable_error(ParseError("bad payload"))
    assert not is_retryable_error(ValidationError("bad schema"))
    assert not is_retryable_error(StorageError("disk full"))

