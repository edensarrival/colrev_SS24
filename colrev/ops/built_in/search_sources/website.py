#! /usr/bin/env python
"""Connector to website (API)"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import requests

import colrev.ops.built_in.search_sources.doi_org as doi_connector
import colrev.record

if TYPE_CHECKING:
    import colrev.ops.prep

# Note: not implemented as a full search_source
# (including SearchSourcePackageEndpointInterface, packages_endpoints.json)


# pylint: disable=too-few-public-methods


class WebsiteConnector:
    """Connector for the Zotero translator for websites"""

    @classmethod
    def __update_record(
        cls,
        prep_operation: colrev.ops.prep.Prep,
        record: colrev.record.Record,
        item: dict,
    ) -> None:
        # pylint: disable=too-many-branches

        record.data["ID"] = item["key"]
        record.data["ENTRYTYPE"] = "article"  # default
        if "journalArticle" == item.get("itemType", ""):
            record.data["ENTRYTYPE"] = "article"
            if "publicationTitle" in item:
                record.data["journal"] = item["publicationTitle"]
            if "volume" in item:
                record.data["volume"] = item["volume"]
            if "issue" in item:
                record.data["number"] = item["issue"]
        if "conferencePaper" == item.get("itemType", ""):
            record.data["ENTRYTYPE"] = "inproceedings"
            if "proceedingsTitle" in item:
                record.data["booktitle"] = item["proceedingsTitle"]
        if "creators" in item:
            author_str = ""
            for creator in item["creators"]:
                author_str += (
                    " and "
                    + creator.get("lastName", "")
                    + ", "
                    + creator.get("firstName", "")
                )
            author_str = author_str[5:]  # drop the first " and "
            record.data["author"] = author_str
        if "title" in item:
            record.data["title"] = item["title"]
        if "doi" in item:
            record.data["doi"] = item["doi"]
        if "date" in item:
            year = re.search(r"\d{4}", item["date"])
            if year:
                record.data["year"] = year.group(0)
        if "pages" in item:
            record.data["pages"] = item["pages"]
        if "url" in item:
            if "https://doi.org/" in item["url"]:
                record.data["doi"] = item["url"].replace("https://doi.org/", "")
                dummy_record = colrev.record.PrepRecord(
                    data={"doi": record.data["doi"]}
                )
                doi_connector.DOIConnector.get_link_from_doi(
                    record=dummy_record,
                    review_manager=prep_operation.review_manager,
                )
                if "https://doi.org/" not in dummy_record.data["url"]:
                    record.data["url"] = dummy_record.data["url"]
            else:
                record.data["url"] = item["url"]

        if "tags" in item:
            if len(item["tags"]) > 0:
                keywords = ", ".join([k["tag"] for k in item["tags"]])
                record.data["keywords"] = keywords

    @classmethod
    def retrieve_md_from_website(
        cls, *, record: colrev.record.Record, prep_operation: colrev.ops.prep.Prep
    ) -> None:
        """Retrieve the metadata the associated website (url) based on Zotero"""

        zotero_translation_service = (
            prep_operation.review_manager.get_zotero_translation_service()
        )

        # Note: retrieve_md_from_url replaces prior data in RECORD
        # (record.copy() - deepcopy() before if necessary)

        zotero_translation_service.start_zotero_translators()

        try:
            content_type_header = {"Content-type": "text/plain"}
            headers = {**prep_operation.requests_headers, **content_type_header}
            export = requests.post(
                "http://127.0.0.1:1969/web",
                headers=headers,
                data=record.data["url"],
                timeout=prep_operation.timeout,
            )

            if export.status_code != 200:
                return

            items = json.loads(export.content.decode())
            if len(items) == 0:
                return
            item = items[0]
            if "Shibboleth Authentication Request" == item["title"]:
                return

            cls.__update_record(prep_operation=prep_operation, record=record, item=item)

        except (
            json.decoder.JSONDecodeError,
            UnicodeEncodeError,
            requests.exceptions.RequestException,
            KeyError,
        ):
            pass


if __name__ == "__main__":
    pass