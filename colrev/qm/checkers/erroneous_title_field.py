#! /usr/bin/env python
"""Checker for erroneous-title-field."""
from __future__ import annotations

import colrev.qm.quality_model

# pylint: disable=too-few-public-methods


class ErroneousTitleFieldChecker:
    """The ErroneousTitleFieldChecker"""

    msg = "erroneous-title-field"

    def __init__(self, quality_model: colrev.qm.quality_model.QualityModel) -> None:
        self.quality_model = quality_model

    def run(self, *, record: colrev.record.Record) -> None:
        """Run the erroneous-title-field checks"""

        if "title" not in record.data:
            return

        if " " not in record.data["title"] and (
            any(x in record.data["title"] for x in ["_", "."])
            or any(char.isdigit() for char in record.data["title"])
        ):
            record.add_masterdata_provenance_note(key="title", note=self.msg)

        else:
            record.remove_masterdata_provenance_note(key="title", note=self.msg)


def register(quality_model: colrev.qm.quality_model.QualityModel) -> None:
    """Register the checker"""
    quality_model.register_checker(ErroneousTitleFieldChecker(quality_model))