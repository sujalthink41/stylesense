import hashlib
from typing import Any

import httpx2 as httpx
import pytest

from stylesense.integrations.media.cloudinary import CloudinaryStore, sign, sign_delivery
from stylesense.modules.uploads.ports import MediaRejectedError, MediaUnavailableError

ASSET = {"public_id": "u/1", "format": "jpg", "bytes": 1234, "width": 800, "height": 1000}


class Recorder:
    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item


def _store(recorder: Recorder) -> CloudinaryStore:
    return CloudinaryStore(
        cloud_name="demo-cloud",
        api_key="1234",
        api_secret="s3cret",
        upload_preset="preset_a",
        client=httpx.AsyncClient(transport=httpx.MockTransport(recorder)),
        now=lambda: 1_700_000_000,
    )


def test_request_signature_follows_cloudinary_rules() -> None:
    payload = b"public_id=a&timestamp=1&upload_preset=p" + b"s3cret"
    expected = hashlib.sha1(payload, usedforsecurity=False).hexdigest()

    assert (
        sign({"upload_preset": "p", "timestamp": "1", "public_id": "a", "empty": ""}, "s3cret")
        == expected
    )


def test_upload_ticket_is_signed_and_names_the_preset() -> None:
    ticket = _store(Recorder(httpx.Response(200))).upload_ticket("u/abc")

    assert ticket.url == "https://api.cloudinary.com/v1_1/demo-cloud/image/upload"
    assert ticket.fields["upload_preset"] == "preset_a"
    assert ticket.fields["timestamp"] == "1700000000"
    signed = {k: ticket.fields[k] for k in ("public_id", "timestamp", "upload_preset")}
    assert ticket.fields["signature"] == sign(signed, "s3cret")
    assert "s3cret" not in str(ticket.fields)


def test_delivery_urls_are_signed_and_private() -> None:
    store = _store(Recorder(httpx.Response(200)))

    url = store.url("u/abc", max_side=768)

    path = "c_limit,h_768,w_768/u/abc.jpg"
    base = "https://res.cloudinary.com/demo-cloud/image/authenticated"
    assert url == f"{base}/{sign_delivery(path, 's3cret')}/{path}"
    assert store.url("u/abc") != store.url("u/abd")


async def test_inspect_returns_the_asset_or_none() -> None:
    recorder = Recorder(httpx.Response(200, json=ASSET), httpx.Response(404))
    store = _store(recorder)

    asset = await store.inspect("u/1")
    missing = await store.inspect("u/2")

    assert (asset.format, asset.bytes, asset.width) == ("jpg", 1234, 800)  # type: ignore[union-attr]
    assert missing is None
    assert recorder.requests[0].url.path == "/v1_1/demo-cloud/resources/image/authenticated/u/1"
    assert recorder.requests[0].headers["authorization"].startswith("Basic ")


async def test_transient_failures_are_retried_once() -> None:
    recorder = Recorder(httpx.Response(503), httpx.Response(200, json=ASSET))

    assert await _store(recorder).inspect("u/1") is not None
    assert len(recorder.requests) == 2


@pytest.mark.parametrize("failure", [httpx.Response(500), httpx.ConnectTimeout("t")])
async def test_persistent_outages_become_media_unavailable(failure: Any) -> None:
    with pytest.raises(MediaUnavailableError):
        await _store(Recorder(failure)).inspect("u/1")


@pytest.mark.parametrize(
    "refusal",
    [
        httpx.Response(400, headers={"x-cld-error": "An unknown file format not allowed"}),
        httpx.Response(401, headers={"x-cld-error": "bad key"}),
    ],
)
async def test_refusals_are_permanent_and_not_retried(refusal: httpx.Response) -> None:
    recorder = Recorder(refusal)

    with pytest.raises(MediaRejectedError):
        await _store(recorder).import_url("https://img.test/a.svg", "t/1")
    assert len(recorder.requests) == 1


async def test_import_url_uploads_from_a_remote_url_with_a_signature() -> None:
    recorder = Recorder(httpx.Response(200, json=ASSET))

    asset = await _store(recorder).import_url("https://img.test/result.jpg", "t/1")

    form = dict(item.split("=", 1) for item in recorder.requests[0].content.decode().split("&"))
    assert asset.public_id == "u/1"
    assert form["public_id"] == "t%2F1"
    assert form["upload_preset"] == "preset_a"
    assert "signature" in form
    assert "authorization" not in recorder.requests[0].headers  # signed form, not basic auth


async def test_delete_batches_by_one_hundred_and_dedupes() -> None:
    recorder = Recorder(httpx.Response(200, json={"deleted": {}}))
    ids = [f"u/{i}" for i in range(150)] + ["u/0"]

    await _store(recorder).delete(ids)

    assert len(recorder.requests) == 2
    assert [len(r.url.params.get_list("public_ids[]")) for r in recorder.requests] == [100, 50]
    assert all(r.method == "DELETE" for r in recorder.requests)
