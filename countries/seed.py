"""
Loading data into PostgreSQL through the Django ORM.

Two jobs:
  1. import_countries()  - turn REST Countries JSON into rows (the "real" data)
  2. inflate()           - add fake rows so index speed-ups are measurable
                           (an index barely matters on 250 rows)

Everything uses bulk_create so loading 250 or 250,000 rows stays fast.
"""
import random

from django.db import transaction

from .models import Country, Currency, Language, Region

# REST Countries v5 (current API). It needs a free API key: https://restcountries.com/sign-up
API_URL = "https://api.restcountries.com/countries/v5"
PAGE_SIZE = 100  # free plan maximum


def _lang_name(value):
    return value if isinstance(value, str) else (value or {}).get("name", "")


def normalise_country(item):
    """Convert ONE country from either REST Countries format into the shape import_countries() uses.

    v5 (current):  {"names": {"common": ..}, "codes": {"alpha_3": ..}, "capitals": [{"name": ..}], ...}
    v3.1 (old):    {"name": {"common": ..}, "cca3": ..., "capital": [..], ...}
    """
    if "names" not in item:  # already the old shape
        return item
    names, codes = item.get("names") or {}, item.get("codes") or {}
    area = item.get("area")
    if isinstance(area, dict):
        area = area.get("kilometers")

    languages = {}
    langs = item.get("languages") or []
    if isinstance(langs, dict):
        languages = {k: _lang_name(v) for k, v in langs.items()}
    else:
        for l in langs:
            if isinstance(l, dict) and l.get("name"):
                key = l.get("iso639_3") or l.get("iso_639_3") or l.get("code") or l.get("bcp47") or l["name"]
                languages[str(key)] = l["name"]

    currencies = {}
    curs = item.get("currencies") or []
    if isinstance(curs, dict):
        for code, v in curs.items():
            v = v if isinstance(v, dict) else {"name": str(v)}
            currencies[code] = {"name": v.get("name", code), "symbol": v.get("symbol", "")}
    else:
        for c in curs:
            if isinstance(c, dict) and c.get("code"):
                currencies[c["code"]] = {"name": c.get("name", c["code"]), "symbol": c.get("symbol", "")}

    return {
        "name": {"common": names.get("common", "")},
        "cca3": codes.get("alpha_3", ""),
        "capital": [c.get("name", "") for c in (item.get("capitals") or []) if isinstance(c, dict)],
        "region": item.get("region") or "",
        "subregion": item.get("subregion") or "",
        "population": item.get("population") or 0,
        "area": area or 0,
        "flag": (item.get("flag") or {}).get("emoji", "") if isinstance(item.get("flag"), dict) else (item.get("flag") or ""),
        "languages": languages,
        "currencies": currencies,
    }


def normalise(raw):
    """Accept a list of countries (old format) or a v5 page {"data": {"objects": [...]}}."""
    if isinstance(raw, dict):
        if "errors" in raw:
            msgs = "; ".join(e.get("message", "?") for e in raw["errors"] if isinstance(e, dict))
            raise ValueError(f"API returned an error: {msgs}")
        raw = (raw.get("data") or {}).get("objects")
        if raw is None:
            raise ValueError("Unexpected API response: no list of countries found.")
    out = [normalise_country(c) for c in raw if isinstance(c, dict)]
    return [c for c in out if c["name"]["common"] and c["cca3"]]


@transaction.atomic
def import_countries(raw):
    """raw = REST Countries data (any supported shape, see normalise). Safe to run repeatedly."""
    raw = normalise(raw)
    # 1) Regions: look up what exists, create what is missing (one bulk insert).
    region_names = {(c.get("region") or "Unknown") for c in raw}
    existing = set(Region.objects.filter(name__in=region_names).values_list("name", flat=True))
    Region.objects.bulk_create([Region(name=n) for n in region_names - existing])
    regions = {r.name: r for r in Region.objects.all()}

    # 2) Languages and currencies, collected from every country first.
    langs, currs = {}, {}
    for c in raw:
        langs.update(c.get("languages") or {})
        for code, info in (c.get("currencies") or {}).items():
            currs[code] = info
    Language.objects.bulk_create(
        [Language(code=k, name=v) for k, v in langs.items()], ignore_conflicts=True
    )
    Currency.objects.bulk_create(
        [Currency(code=k, name=v.get("name", k), symbol=v.get("symbol", "") or "") for k, v in currs.items()],
        ignore_conflicts=True,
    )
    lang_by_code = {l.code: l for l in Language.objects.all()}
    curr_by_code = {c.code: c for c in Currency.objects.all()}

    # 3) Countries: upsert on cca3 so re-running updates instead of duplicating.
    rows = [
        Country(
            name=c["name"]["common"],
            cca3=c["cca3"],
            capital=(c.get("capital") or [""])[0],
            flag=c.get("flag", "") or "",
            population=c.get("population") or 0,
            area=c.get("area") or 0,
            region=regions[c.get("region") or "Unknown"],
        )
        for c in raw
    ]
    Country.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["cca3"],
        update_fields=["name", "capital", "flag", "population", "area", "region"],
    )

    # 4) Many-to-many links go through the hidden "through" tables.
    by_cca3 = dict(Country.objects.filter(cca3__in=[c["cca3"] for c in raw]).values_list("cca3", "id"))
    LangThrough = Country.languages.through
    CurrThrough = Country.currencies.through
    ids = list(by_cca3.values())
    LangThrough.objects.filter(country_id__in=ids).delete()
    CurrThrough.objects.filter(country_id__in=ids).delete()
    lang_links, curr_links = [], []
    for c in raw:
        cid = by_cca3[c["cca3"]]
        lang_links += [LangThrough(country_id=cid, language_id=lang_by_code[k].id) for k in (c.get("languages") or {})]
        curr_links += [CurrThrough(country_id=cid, currency_id=curr_by_code[k].id) for k in (c.get("currencies") or {})]
    LangThrough.objects.bulk_create(lang_links)
    CurrThrough.objects.bulk_create(curr_links)
    return {"countries": len(rows), "languages": len(langs), "currencies": len(currs), "regions": len(region_names)}


def synthetic_rows(n, prefix="SYN", start=0, regions=None, seed=None):
    """Build n unsaved fake Country objects with realistic-looking populations."""
    rnd = random.Random(seed)
    regions = regions or list(Region.objects.all())
    out = []
    for i in range(start, start + n):
        # log-normal: a few huge countries, many small ones, like the real world
        pop = int(min(rnd.lognormvariate(14.5, 2.0), 1.6e9))
        out.append(
            Country(
                name=f"Synthland {i:07d}",
                cca3=f"{prefix}{i:07d}"[:12],
                capital=f"Capital {i}",
                population=pop,
                area=round(rnd.uniform(10, 2_000_000), 1),
                region=rnd.choice(regions),
                is_synthetic=True,
            )
        )
    return out


def inflate(n):
    start = Country.objects.filter(is_synthetic=True).count()
    for chunk_start in range(0, n, 20_000):
        size = min(20_000, n - chunk_start)
        Country.objects.bulk_create(synthetic_rows(size, start=start + chunk_start), batch_size=5_000)
    return n


def remove_synthetic():
    deleted, _ = Country.objects.filter(is_synthetic=True).delete()
    return deleted
