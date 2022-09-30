#! /usr/bin/env python
from __future__ import annotations

from typing import TYPE_CHECKING

import zope.interface
from dacite import from_dict

import colrev.operation

if TYPE_CHECKING:
    import colrev.ops.pdf_get


@zope.interface.implementer(colrev.env.package_manager.PDFGetPackageInterface)
class CustomPDFGet:
    def __init__(
        self, *, pdf_get_operation: colrev.ops.pdf_get.PDFGet, settings: dict
    ) -> None:
        self.settings = from_dict(
            data_class=colrev.env.package_manager.DefaultSettings, data=settings
        )

    def get_pdf(
        self, pdf_get_operation: colrev.ops.pdf_get.PDFGet, record: colrev.record.Record
    ) -> colrev.record.Record:

        record.data["file"] = "filepath"
        record.import_file(review_manager=pdf_get_operation.review_manager)

        return record