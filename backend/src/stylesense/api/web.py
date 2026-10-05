"""Public web pages for share links (/l/{slug}) and polls (/p/{slug}).

Server-rendered so link previews (WhatsApp, Instagram) get a title and image without running
JavaScript. Nothing about the owner is shown. Store buttons go through /v1/out (tracked,
allow-listed redirects). Interim until the CP18 web app; the URLs stay the same.
"""

import json
from html import escape
from importlib.resources import files
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import HTMLResponse

from stylesense.api.dependencies import ContainerDep
from stylesense.api.rate_limit import rate_limited
from stylesense.modules.catalog.schemas import ProductSummary
from stylesense.platform.errors import AppError

_ASSETS = files("stylesense.api").joinpath("web_assets")
_CSS = _ASSETS.joinpath("page.css").read_text(encoding="utf-8")
_POLL_JS = _ASSETS.joinpath("poll.js").read_text(encoding="utf-8")

router = APIRouter(include_in_schema=False, dependencies=[Depends(rate_limited("public.per_ip"))])
Slug = Annotated[str, Path(pattern=r"^[A-Za-z0-9]{6,16}$")]
STORES = {"amazon": "Amazon", "flipkart": "Flipkart", "myntra": "Myntra"}


def _rupees(paise: int | None) -> str:
    """Whole rupees with Indian digit grouping (1,23,456), like the app."""
    if paise is None:
        return "Out of stock"
    digits = str(round(paise / 100))
    head, tail = digits[:-3], digits[-3:]
    pairs: list[str] = []
    while len(head) > 2:  # noqa: PLR2004
        pairs.insert(0, head[-2:])
        head = head[:-2]
    return "₹" + ",".join([g for g in [head, *pairs] if g] + [tail])


async def _best_offer(container: ContainerDep, p: ProductSummary) -> tuple[str, str] | None:
    """(offer id, store name) to send the shopper to: the best priced offer, or else any
    in-stock listing whose price we don't know yet ("See price on …")."""
    try:
        detail = await container.catalog.get_product(p.id)
    except AppError:
        return None
    offers = [o for o in detail.offers if o.in_stock]
    best = next((o for o in offers if o.is_best), None) or next(iter(offers), None)
    return (str(best.id), best.store_name) if best else None


@router.get("/l/{slug}", response_class=HTMLResponse)
async def share_page(slug: Slug, container: ContainerDep) -> HTMLResponse:
    try:
        share = await container.sharing.open(slug)
    except AppError as e:
        return _message_page(
            "This link has expired", "The person who shared it may have removed it.", e.status_code
        )
    title = share.title or (
        "A look on StyleSense" if share.kind == "look" else "Picks on StyleSense"
    )
    cards = []
    for p in share.products:
        offer = await _best_offer(container, p)
        cards.append(_product_card(p, offer))
    image = next((p.primary_image_url for p in share.products if p.primary_image_url), None)
    body = f"""
    <header class="band"><div class="brand">{_LOGO}<span>StyleSense</span></div>
      <p class="eyebrow">Shared with you</p><h1>{escape(title)}</h1>
      <p class="sub">Live prices across Amazon, Flipkart and Myntra.</p></header>
    <main class="grid">{"".join(cards)}</main>
    {_FOOTER}"""
    return _page(title, f"{len(share.products)} picks with live prices", image, body)


@router.get("/p/{slug}", response_class=HTMLResponse)
async def poll_page(slug: Slug, container: ContainerDep) -> HTMLResponse:
    try:
        poll = await container.polls.public(slug, voter_token=None)
    except AppError as e:
        return _message_page(
            "This poll is gone",
            "It may have been deleted by the person who made it.",
            e.status_code,
        )
    options = "".join(
        f"""<button class="option" data-id="{o.option_id}" type="button">
          <div class="photo">{_img(o.product.primary_image_url, o.product.title)}<span class="tick">✓</span></div>
          <div class="meta"><span class="brandname">{escape(o.product.brand)}</span>
            <span class="title">{escape(o.product.title)}</span>
            <span class="price">{_rupees(o.product.min_price_paise)}</span>
            <span class="bar"><span class="fill"></span></span><span class="count"></span></div>
        </button>"""
        for o in poll.options
    )
    image = next(
        (o.product.primary_image_url for o in poll.options if o.product.primary_image_url), None
    )
    state = json.dumps({"slug": slug, "open": poll.status == "open"})
    body = f"""
    <header class="band"><div class="brand">{_LOGO}<span>StyleSense</span></div>
      <p class="eyebrow">A friend needs your vote</p><h1>{escape(poll.question)}</h1>
      <p class="sub" id="status">{"Tap the one you'd pick. No sign-in needed." if poll.status == "open" else "Voting has closed."}</p></header>
    <main class="poll">{options}</main>
    {_FOOTER}
    <script>window.POLL={state};</script><script>{_POLL_JS}</script>"""
    return _page(poll.question, "Help pick: tap the one you'd buy.", image, body)


def _img(url: str | None, alt: str) -> str:
    return (
        f'<img src="{escape(url)}" alt="{escape(alt)}" loading="lazy">'
        if url
        else '<div class="noimg"></div>'
    )


def _product_card(p: ProductSummary, offer: tuple[str, str] | None) -> str:
    if offer is None:
        cta, price = '<span class="soldout">Out of stock</span>', _rupees(None)
    else:
        offer_id, store = offer
        label = f"Shop on {store}" if p.min_price_paise is not None else f"See price on {store}"
        cta = f'<a class="buy" href="/v1/out/{escape(offer_id)}?src=share" rel="nofollow sponsored">{escape(label)} →</a>'
        price = _rupees(p.min_price_paise) if p.min_price_paise is not None else ""
    return f"""<article class="card"><div class="photo">{_img(p.primary_image_url, p.title)}</div>
      <div class="meta"><span class="brandname">{escape(p.brand)}</span><span class="title">{escape(p.title)}</span>
      <span class="price">{price}</span>{cta}</div></article>"""


def _message_page(title: str, text: str, status: int) -> HTMLResponse:
    body = f"""<header class="band tall"><div class="brand">{_LOGO}<span>StyleSense</span></div>
      <h1>{escape(title)}</h1><p class="sub">{escape(text)}</p></header>{_FOOTER}"""
    return _page(title, text, None, body, status=status)


def _page(
    title: str, description: str, image: str | None, body: str, *, status: int = 200
) -> HTMLResponse:
    og_image = f'<meta property="og:image" content="{escape(image)}">' if image else ""
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{escape(title)} · StyleSense</title><meta name="description" content="{escape(description)}">
<meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(description)}">
{og_image}<meta property="og:site_name" content="StyleSense"><meta name="theme-color" content="#1F2B5C">
<meta name="robots" content="noindex">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anek+Latin:wdth,wght@75..125,400..800&display=swap" rel="stylesheet">
<style>{_CSS}</style></head><body>{body}</body></html>"""
    return HTMLResponse(
        html,
        status_code=status,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


_LOGO = (
    '<svg width="28" height="28" viewBox="0 0 56 56" aria-hidden="true"><rect width="56" height="56" rx="14" fill="#F2F3F7"/>'
    '<g transform="translate(28 28)" fill="#1F2B5C">'
    + "".join(
        f'<ellipse cx="0" cy="-12" rx="4.2" ry="8" transform="rotate({i * 45})"/>' for i in range(8)
    )
    + '<circle r="4.5" fill="#F2F3F7"/><circle r="2.2" fill="#B8322A"/></g></svg>'
)

_FOOTER = "<footer>Prices update live. Store links may earn StyleSense a commission; it never changes the picks.</footer>"
