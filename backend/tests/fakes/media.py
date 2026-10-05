from collections.abc import Sequence

from stylesense.modules.tryon.ports import TryOnRejectedError, TryOnResult, TryOnRetryableError
from stylesense.modules.uploads.ports import (
    MediaRejectedError,
    MediaUnavailableError,
    StoredAsset,
    UploadTicket,
)

GOOD = StoredAsset(public_id="", format="jpg", bytes=180_000, width=1200, height=1600)


class FakeMediaStore:
    """In-memory storage. `simulate_upload` plays the app uploading to the signed slot."""

    name = "fake"

    def __init__(self) -> None:
        self.assets: dict[str, StoredAsset] = {}
        self.deleted: list[str] = []
        self.imported: list[tuple[str, str]] = []
        self.down = False

    def simulate_upload(self, public_id: str, asset: StoredAsset = GOOD) -> None:
        self.assets[public_id] = StoredAsset(
            public_id, asset.format, asset.bytes, asset.width, asset.height
        )

    def upload_ticket(self, public_id: str) -> UploadTicket:
        return UploadTicket(
            url="https://upload.test/image/upload",
            fields={"public_id": public_id, "signature": "sig", "timestamp": "1"},
        )

    async def inspect(self, public_id: str) -> StoredAsset | None:
        self._check()
        return self.assets.get(public_id)

    def url(self, public_id: str, *, max_side: int | None = None) -> str:
        return f"https://cdn.test/{public_id}?side={max_side}&sig=ok"

    async def import_url(self, source_url: str, public_id: str) -> StoredAsset:
        self._check()
        if source_url.endswith(".svg"):
            raise MediaRejectedError("unknown file format")
        self.imported.append((source_url, public_id))
        self.simulate_upload(public_id)
        return self.assets[public_id]

    async def delete(self, public_ids: Sequence[str]) -> None:
        self._check()
        for pid in public_ids:
            self.assets.pop(pid, None)
            self.deleted.append(pid)

    def _check(self) -> None:
        if self.down:
            raise MediaUnavailableError("fake storage is down")


class ScriptedTryOn:
    """Try-on provider that counts calls and can fail on demand."""

    name = "scripted"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.failures: list[Exception] = []
        self.result_url: str | None = None  # override what the "vendor" returns

    async def render(
        self, *, person_url: str, garment_url: str, idempotency_key: str
    ) -> TryOnResult:
        self.calls.append(idempotency_key)
        if self.failures:
            raise self.failures.pop(0)
        return TryOnResult(
            image_url=self.result_url or f"https://vendor.test/{idempotency_key}.jpg",
            cost_micro_usd=40_000,
        )

    def busy(self, times: int = 1) -> None:
        self.failures += [TryOnRetryableError("busy")] * times

    def refuse(self) -> None:
        self.failures.append(TryOnRejectedError("no person"))
