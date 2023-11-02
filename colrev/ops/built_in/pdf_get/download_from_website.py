#! /usr/bin/env python
"""Retrieval of PDFs from the website (URL)"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin


import requests
import zope.interface
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.record
from colrev.constants import Fields

# pylint: disable=duplicate-code
# pylint: disable=too-few-public-methods


@zope.interface.implementer(colrev.env.package_manager.PDFGetPackageEndpointInterface)
@dataclass
class WebsiteDownload(JsonSchemaMixin):
    """Get PDFs from the website"""

    settings_class = colrev.env.package_manager.DefaultSettings
    ci_supported: bool = False

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "TE": "Trailers",
    }

    def __init__(
        self,
        *,
        pdf_get_operation: colrev.ops.pdf_get.PDFGet,
        settings: dict,
    ) -> None:
        self.settings = self.settings_class.load_settings(data=settings)
        self.review_manager = pdf_get_operation.review_manager
        self.pdf_get_operation = pdf_get_operation

    def __download_from_jmir(
        self, *, record: colrev.record.Record, pdf_filepath: Path
    ) -> None:
        article_url = record.data[Fields.URL]
        response = requests.get(article_url, headers=self.headers)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")

            pdf_link = soup.find("a", {"data-test": "pdf-button"})

            if pdf_link:
                pdf_url = urljoin(article_url, pdf_link["href"])

                paper_title_tag = soup.find("meta", {"name": "citation_title"})
                if paper_title_tag:
                    pdf_response = requests.get(pdf_url)

                    if pdf_response.status_code == 200:
                        with open(pdf_filepath, "wb") as pdf_file:
                            pdf_file.write(pdf_response.content)
                        self.review_manager.logger.debug(
                            f"PDF downloaded successfully as {pdf_filepath}"
                        )
                    else:
                        self.review_manager.logger.debug(
                            f"Failed to download PDF. Status code: {pdf_response.status_code}"
                        )
                else:
                    self.review_manager.logger.debug(
                        "Paper title not found on the page."
                    )
            else:
                self.review_manager.logger.debug("PDF link not found on the page.")
        else:
            self.review_manager.logger.debug(
                f"Failed to retrieve the article page. Status code: {response.status_code}"
            )

    def __download_from_bmj_open_science(
        self, *, record: colrev.record.Record, pdf_filepath: Path
    ) -> None:
        url = record.data[Fields.URL]
        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")

            pdf_link = soup.find("a", {"class": "article-pdf-download"})

            if pdf_link:
                pdf_url = pdf_link.get("href")

                if pdf_url:
                    if not pdf_url.startswith(("http:", "https:")):
                        pdf_url = urljoin(url, pdf_url)

                    pdf_response = requests.get(pdf_url)

                    if pdf_response.status_code == 200:
                        with open(pdf_filepath, "wb") as pdf_file:
                            pdf_file.write(pdf_response.content)

                        self.review_manager.logger.debug(
                            f"PDF downloaded successfully as {pdf_filepath}"
                        )
                    else:
                        self.review_manager.logger.debug(
                            f"Failed to download PDF. Status code: {pdf_response.status_code}"
                        )
                else:
                    self.review_manager.logger.debug("PDF URL not found on the page.")
            else:
                self.review_manager.logger.debug("PDF link not found on the page.")
        else:
            self.review_manager.logger.debug(
                f"Failed to retrieve the article page. Status code: {response.status_code}"
            )

    def __download_unknown(
        self, *, record: colrev.record.Record, pdf_filepath: Path
    ) -> None:
        url = record.data[Fields.URL]
        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")

            pdf_link = soup.find("a", text="PDF")
            if not pdf_link:
                pdf_link = soup.find(
                    "a", href=lambda href: href and href.endswith(".pdf")
                )

            if pdf_link:
                pdf_url = pdf_link.get("href")

                if pdf_url:
                    if not pdf_url.startswith(("http:", "https:")):
                        pdf_url = urljoin(url, pdf_url)

                    pdf_response = requests.get(pdf_url)

                    if pdf_response.status_code == 200:
                        with open(pdf_filepath, "wb") as pdf_file:
                            pdf_file.write(pdf_response.content)

                        self.review_manager.logger.debug(
                            f"PDF downloaded successfully as {pdf_filepath}"
                        )
                    else:
                        self.review_manager.logger.debug(
                            f"Failed to download PDF. Status code: {pdf_response.status_code}"
                        )
                else:
                    self.review_manager.logger.debug("PDF URL not found on the page.")
            else:
                self.review_manager.logger.debug("PDF link not found on the page.")
        else:
            self.review_manager.logger.debug(
                f"Failed to retrieve the Minerva Medica page. Status code: {response.status_code}"
            )

    def get_pdf(
        self, pdf_get_operation: colrev.ops.pdf_get.PDFGet, record: colrev.record.Record
    ) -> colrev.record.Record:
        """Get PDFs from website (URL)"""

        if Fields.URL not in record.data:
            return record

        pdf_filepath = pdf_get_operation.get_target_filepath(record=record)

        try:
            if any(
                x in record.data[Fields.URL]
                for x in ["jmir.org", "iproc.org", "researchprotocols.org"]
            ):
                self.__download_from_jmir(record=record, pdf_filepath=pdf_filepath)

            if "bmjopensem.bmj.com" in record.data[Fields.URL]:
                self.__download_from_bmj_open_science(
                    record=record, pdf_filepath=pdf_filepath
                )

            else:
                self.__download_unknown(record=record, pdf_filepath=pdf_filepath)

            if pdf_filepath.is_file():
                record.update_field(
                    key=Fields.FILE, value=str(pdf_filepath), source="website-download"
                )
                self.pdf_get_operation.import_pdf(record=record)
        except requests.RequestException:
            pass

        return record
