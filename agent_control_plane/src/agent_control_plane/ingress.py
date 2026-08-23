"""Browser-facing Home Assistant Ingress helpers."""


def cookie_secure(request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    return (forwarded or request.url.scheme.lower()) == "https"
