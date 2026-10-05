from stylesense.modules.tryon.ports import TryOnResult


class FakeTryOnProvider:
    """Local testing only (refused in production): "renders" by returning the garment image.

    Lets the whole pipeline (jobs, storage, purge, reports) run end to end with no paid vendor.
    """

    name = "fake"

    async def render(
        self, *, person_url: str, garment_url: str, idempotency_key: str
    ) -> TryOnResult:
        return TryOnResult(image_url=garment_url, cost_micro_usd=0)  # a raster image URL
