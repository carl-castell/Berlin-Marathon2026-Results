"""Step 1: the results lists (100 runners per page, separated by sex).

The site's sex filter: M = men, W = women, X = diverse.

Usage:
    uv run scrapy crawl results_list
    uv run scrapy crawl results_list -a sex=W -a max_pages=2   # for testing

Flow:
    start()  -> request page 1 for each sex
    parse()  -> emit the page's runners as RunnerItems
                (page 1 only) find the last page number and request all other
                pages at once -> Scrapy downloads them in parallel.
"""

import re
from urllib.parse import parse_qs, urlparse

import scrapy
from scrapy.exceptions import CloseSpider

from ..items import RunnerItem
from ..site import clean, decode_silver, detail_url, list_url, to_int
from .base import ProgressSpider

# Every field contains a label <div class="list-label"> for the mobile view,
# e.g. <div>  <div class="list-label">Bib Number</div>6  </div>.
# This XPath takes all text in the field EXCEPT the text inside the label.
VALUE_XPATH = ".//text()[not(ancestor::div[contains(@class, 'list-label')])]"


def field_value(el) -> str | None:
    return clean("".join(el.xpath(VALUE_XPATH).getall()))


# "Last name, First name (NAT)": nation = three capital letters in parentheses at the end.
NATION_RE = re.compile(r"\s*\(([A-Z]{3})\)$")


def split_name(full_name: str) -> tuple[str, str | None, str | None]:
    """'Adola, Guye (ETH)' -> ('Adola', 'Guye', 'ETH').

    The site always writes "Last name, First name". We split at the first
    comma; without a comma everything counts as the last name.
    """
    nation = None
    m = NATION_RE.search(full_name)
    if m:
        nation = m.group(1)
        full_name = full_name[: m.start()]
    last, sep, first = full_name.partition(",")
    return last.strip(), (first.strip() or None) if sep else None, nation


class ResultsListSpider(ProgressSpider):
    name = "results_list"
    progress_label = "Lists"
    allowed_domains = ["berlin.r.mikatiming.com"]

    def __init__(self, sex: str = "M,W,X", max_pages: str | None = None, **kwargs):
        # Arguments passed with -a always arrive as strings.
        super().__init__(**kwargs)
        self.sexes = [s.strip() for s in sex.split(",")]
        self.max_pages = int(max_pages) if max_pages else None

    async def start(self):
        # Since Scrapy 2.13 `async def start()` is the entry point (formerly start_requests()).
        # We only know the total number of pages after page 1 -> count just those for now.
        self.add_total(len(self.sexes))
        for sex in self.sexes:
            # cb_kwargs: extra arguments passed to the callback.
            # That way parse() knows which sex/page the response belongs to.
            yield scrapy.Request(
                list_url(sex, 1),
                callback=self.parse,
                errback=self.on_error,
                cb_kwargs={"sex": sex, "page": 1},
            )

    def parse(self, response, sex: str, page: int):
        # Safety check: the site silently ignores unknown filter values and then
        # shows the men (tested with "D"). The site writes the filter that is
        # actually active into <div data-sex="...">.
        active = response.css("[data-sex]::attr(data-sex)").get()
        if active != sex:
            raise CloseSpider(f"Filter sex={sex} has no effect (page shows data-sex={active!r})")

        rows = response.css("li.list-group-item.row:not(.list-group-header)")
        self.logger.debug("%s page %d: %d runners", sex, page, len(rows))

        for row in rows:
            yield self.parse_row(row, response, sex, page)

        if page == 1:
            last = self.last_page(response)
            if self.max_pages:
                last = min(last, self.max_pages)
            self.logger.info("%s: %d pages in total", sex, last)
            self.add_total(last - 1)
            for p in range(2, last + 1):
                yield scrapy.Request(
                    list_url(sex, p),
                    callback=self.parse,
                    errback=self.on_error,
                    cb_kwargs={"sex": sex, "page": p},
                )

        self.mark_done()

    def parse_row(self, row, response, sex: str, page: int) -> RunnerItem:
        # Name link: "Adola, Guye (ETH)" with href="?content=detail&...&idp=..."
        link = row.css("h4.type-fullname a")
        full_name = clean(link.css("::text").get())
        href = link.attrib["href"]
        idp = parse_qs(urlparse(href).query)["idp"][0]

        last_name, first_name, nation = split_name(full_name or "")

        # Right-hand columns, in fixed order:
        #   .pull-left:  bib | age group | club
        #   .pull-right: gun time | net time | (favorite icon)
        left = [field_value(el) for el in row.css(".pull-left .list-field")]
        times = [field_value(el) for el in row.css(".pull-right .type-time")]
        bib, age_class, club = (left + [None] * 3)[:3]

        return RunnerItem(
            idp=idp,
            sex=sex,
            place_overall=to_int(row.css(".place-primary::text").get()),
            place_ak=to_int(row.css(".place-secondary::text").get()),
            last_name=last_name,
            first_name=first_name,
            nation=nation,
            bib=bib,
            age_class=age_class,
            club=club,
            time_brutto=times[0] if len(times) > 0 else None,
            time_netto=times[1] if len(times) > 1 else None,
            detail_url=detail_url(idp),
            list_page=page,
        )

    def last_page(self, response) -> int:
        """Read the highest page number from the (encoded) pagination links."""
        pages = [1]
        for code in response.css("ul.pagination a::attr(data-silver)").getall():
            m = re.search(r"[?&]page=(\d+)", decode_silver(code))
            if m:
                pages.append(int(m.group(1)))
        return max(pages)
