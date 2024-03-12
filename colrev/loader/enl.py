#! /usr/bin/env python
"""Convenience functions to load ENL files"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

import colrev.loader.loader

if TYPE_CHECKING:  # pragma: no cover
    import typing
    from typing import Callable

# pylint: disable=too-few-public-methods
# pylint: disable=too-many-arguments
# pylint: disable=too-many-instance-attributes


class NextLine(Exception):
    """NextLineException"""


class ParseError(Exception):
    """Parsing error"""


class ENLLoader(colrev.loader.loader.Loader):
    """Loads enl files"""

    PATTERN = r"^%[A-Z]{1,3} "

    # pylint: disable=too-many-arguments
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

        self.current: dict = {}
        self.pattern = re.compile(self.PATTERN)

    def _get_tag(self, line: str) -> str:
        """Get the tag from a line in the ENL file."""
        return line[1:3].rstrip()

    def _get_content(self, line: str) -> str:
        """Get the content from a line"""
        return line[2:].strip()

    def _add_tag(self, tag: str, line: str) -> None:
        new_value = self._get_content(line)

        if tag not in self.current:
            self.current[tag] = new_value
        elif isinstance(self.current[tag], str):
            self.current[tag] = [self.current[tag], new_value]
        elif isinstance(self.current[tag], list):
            self.current[tag].append(new_value)

    def _parse_tag(self, line: str) -> dict:
        tag = self._get_tag(line)

        if tag.strip() == "":
            return self.current

        self._add_tag(tag, line)
        raise NextLine

    def _parse_lines(self, lines: list) -> typing.Iterator[dict]:
        for line in lines:
            try:
                yield self._parse_tag(line)
                self.current = {}
            except NextLine:
                continue

    def load_records_list(self) -> list:
        """Loads enl entries"""

        # based on
        # https://github.com/MrTango/rispy/blob/main/rispy/parser.py
        # Note: skip-tags and unknown-tags can be handled
        # between load_enl_entries and convert_to_records.

        text = self.filename.read_text(encoding="utf-8")
        # clean_text?
        lines = text.split("\n")
        records_list = list(r for r in self._parse_lines(lines) if r)
        return records_list
