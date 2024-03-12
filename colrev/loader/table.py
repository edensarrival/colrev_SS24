#! /usr/bin/env python
"""Convenience functions to load tabular files (csv, xlsx)"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

import colrev.exceptions as colrev_exceptions
import colrev.loader.loader

if TYPE_CHECKING:  # pragma: no cover
    from typing import Callable

# pylint: disable=too-few-public-methods
# pylint: disable=too-many-arguments


class TableLoader(colrev.loader.loader.Loader):
    """Loads csv and Excel files (based on pandas)"""

    def __init__(
        self,
        *,
        filename: Path,
        entrytype_setter: Callable,
        field_mapper: Callable,
        id_labeler: Callable,
        unique_id_field: str = "",
        logger: logging.Logger = logging.getLogger(__name__),
    ):
        super().__init__(
            filename=filename,
            id_labeler=id_labeler,
            unique_id_field=unique_id_field,
            entrytype_setter=entrytype_setter,
            field_mapper=field_mapper,
            logger=logger,
        )

    def load_records_list(self) -> list:
        try:
            if self.filename.name.endswith(".csv"):
                data = pd.read_csv(self.filename)
            elif self.filename.name.endswith((".xls", ".xlsx")):
                data = pd.read_excel(
                    self.filename, dtype=str
                )  # dtype=str to avoid type casting

        except pd.errors.ParserError as exc:  # pragma: no cover
            raise colrev_exceptions.ImportException(
                f"Error: Not a valid file? {self.filename.name}"
            ) from exc

        records_list = data.to_dict("records")
        return records_list
