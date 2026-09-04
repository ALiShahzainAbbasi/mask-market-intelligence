from email.message import Message

from mask_api.modules.evidence.contracts import FetchedResource
from mask_api.modules.evidence.errors import ParseFailure

_ALLOWED_ENCODINGS = {
    "ascii",
    "iso-8859-1",
    "latin-1",
    "utf-8",
    "utf8",
    "windows-1252",
}


def decode_resource(resource: FetchedResource) -> str:
    message = Message()
    message["content-type"] = resource.content_type
    encoding = (message.get_content_charset() or "utf-8").lower()
    if encoding not in _ALLOWED_ENCODINGS:
        raise ParseFailure(
            "collection.unsupported_encoding",
            "The response declared an unsupported text encoding.",
        )
    try:
        return resource.body.decode(encoding, errors="strict")
    except (LookupError, UnicodeDecodeError) as exc:
        raise ParseFailure(
            "collection.invalid_encoding",
            "The response body does not match its declared text encoding.",
        ) from exc
