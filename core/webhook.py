import json
import urllib.error
import urllib.request


class WebhookError(Exception):
    pass


def post_json(url, payload, timeout):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        raise WebhookError(f"the alert address answered {e.code}") from e
    except (urllib.error.URLError, OSError) as e:
        raise WebhookError(f"the alert address could not be reached: {e}") from e
