from typing import Any, cast

from .errors import ValidationError


def validate_parliament_api_payload(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValidationError("Parliament API payload must be an object")
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("items"), list):
        raise ValidationError("Parliament API result.items must be a list")
    if not all(isinstance(item, dict) for item in result["items"]):
        raise ValidationError("Parliament API items must be objects")
    return cast(list[dict[str, Any]], result["items"])
