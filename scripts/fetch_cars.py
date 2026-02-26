#!/usr/bin/env python3
"""Fetch Honda N-VAN Turbo White listings from carsensor.net and export JSON."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

BASE_URL = "https://www.carsensor.net"
SEARCH_URL = (
    "https://www.carsensor.net/usedcar/freeword/"
    "Honda+N-VAN+%E3%82%BF%E3%83%BC%E3%83%9C+%E3%83%9B%E3%83%AF%E3%82%A4%E3%83%88/index.html"
)


class JsonLdExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_json_ld = False
        self._buf: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k.lower(): v for k, v in attrs}
        if tag.lower() == "script" and (attr_map.get("type") or "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_json_ld:
            raw = "".join(self._buf).strip()
            if raw:
                self.blocks.append(raw)
            self._in_json_ld = False
            self._buf = []


@dataclass
class Listing:
    title: str
    price_yen: int | None
    price_label: str
    location: str
    image_url: str
    detail_url: str
    source: str = "carsensor.net"


def normalize_price(text: str) -> int | None:
    cleaned = text.replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*万円", cleaned)
    if match:
        return int(float(match.group(1)) * 10000)
    match = re.search(r"([0-9]+)\s*円", cleaned)
    if match:
        return int(match.group(1))
    return None


def parse_json_ld(html: str) -> list[Listing]:
    parser = JsonLdExtractor()
    parser.feed(html)

    listings: list[Listing] = []
    for raw in parser.blocks:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        items: Iterable[dict] = []
        if isinstance(data, dict):
            if "itemListElement" in data and isinstance(data["itemListElement"], list):
                items = [
                    x.get("item", x)
                    for x in data["itemListElement"]
                    if isinstance(x, dict)
                ]
            else:
                items = [data]
        elif isinstance(data, list):
            items = [x for x in data if isinstance(x, dict)]

        for item in items:
            title = str(item.get("name", "")).strip()
            if not title:
                continue

            offers = item.get("offers", {}) if isinstance(item.get("offers"), dict) else {}
            price = offers.get("price")
            price_currency = offers.get("priceCurrency")
            price_yen = None
            price_label = ""
            if price is not None:
                try:
                    price_yen = int(float(str(price)))
                except ValueError:
                    price_yen = normalize_price(str(price))
                if price_yen is not None:
                    price_label = f"{price_yen:,} 円"
                else:
                    price_label = f"{price} {price_currency or ''}".strip()

            area = item.get("areaServed") or item.get("address") or ""
            if isinstance(area, dict):
                area = " ".join(str(v) for v in area.values() if v)

            image = item.get("image")
            if isinstance(image, list):
                image_url = urljoin(BASE_URL, str(image[0])) if image else ""
            else:
                image_url = urljoin(BASE_URL, str(image or ""))

            detail_url = urljoin(BASE_URL, str(item.get("url") or ""))

            listings.append(
                Listing(
                    title=title,
                    price_yen=price_yen,
                    price_label=price_label,
                    location=str(area),
                    image_url=image_url,
                    detail_url=detail_url,
                )
            )

    return listings


def parse_fallback_html(html: str) -> list[Listing]:
    """Best-effort parser when JSON-LD is absent."""
    listings: list[Listing] = []
    pattern = re.compile(
        r'<a[^>]+href="(?P<url>/usedcar/detail/[^\"]+)"[^>]*>(?P<title>[^<]{2,200})</a>',
        re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        title = re.sub(r"\s+", " ", match.group("title")).strip()
        if not title:
            continue
        detail_url = urljoin(BASE_URL, match.group("url"))
        listings.append(
            Listing(
                title=title,
                price_yen=None,
                price_label="",
                location="",
                image_url="",
                detail_url=detail_url,
            )
        )
        if len(listings) >= 60:
            break
    return listings


def scrape() -> list[Listing]:
    req = Request(
        SEARCH_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        },
    )
    with urlopen(req, timeout=30) as resp:  # noqa: S310
        html = resp.read().decode("utf-8", errors="ignore")

    listings = parse_json_ld(html)
    if not listings:
        listings = parse_fallback_html(html)

    uniq: dict[str, Listing] = {}
    for item in listings:
        key = item.detail_url or f"{item.title}-{item.price_label}-{item.location}"
        uniq[key] = item

    return list(uniq.values())


def apply_filters(
    listings: list[Listing],
    max_price: int | None,
    region_keyword: str | None,
) -> list[Listing]:
    filtered = listings

    if max_price is not None:
        filtered = [
            item for item in filtered if item.price_yen is None or item.price_yen <= max_price
        ]

    if region_keyword:
        region_kw = region_keyword.lower()
        filtered = [item for item in filtered if region_kw in item.location.lower()]

    return filtered


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-price", type=int, default=None, help="Max price in JPY")
    parser.add_argument("--region", type=str, default=None, help="Region keyword filter")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/listings.json"),
        help="Output JSON path",
    )
    args = parser.parse_args()

    try:
        listings = scrape()
        error = None
    except Exception as exc:  # noqa: BLE001
        listings = []
        error = str(exc)

    listings = apply_filters(listings, args.max_price, args.region)

    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "source": SEARCH_URL,
        "query": {
            "model": "Honda N-VAN",
            "color": "white",
            "feature": "turbo",
            "max_price": args.max_price,
            "region": args.region,
        },
        "error": error,
        "count": len(listings),
        "items": [asdict(item) for item in listings],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
