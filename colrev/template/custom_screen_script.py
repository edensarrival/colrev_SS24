#! /usr/bin/env python
from __future__ import annotations

import random
from typing import TYPE_CHECKING

import zope.interface
from dacite import from_dict

import colrev.operation
import colrev.record

if TYPE_CHECKING:
    import colrev.screen.Screen


@zope.interface.implementer(colrev.env.package_manager.ScreenPackageInterface)
class CustomScreen:
    def __init__(
        self, *, screen_operation: colrev.screen.Screen, settings: dict
    ) -> None:
        self.settings = from_dict(
            data_class=colrev.env.package_manager.DefaultSettings, data=settings
        )

    def run_screen(
        self, screen_operation: colrev.screen.Screen, records: dict, split: list
    ) -> dict:

        screen_data = screen_operation.get_data()
        screening_criteria = screen_operation.review_manager.settings.screen.criteria

        if screening_criteria:
            screening_criteria_available = True
        else:
            screening_criteria_available = False

        for record_dict in screen_data["items"]:
            if len(split) > 0:
                if record_dict["ID"] not in split:
                    continue

            screen_record = colrev.record.ScreenRecord(data=record_dict)

            if random.random() < 0.5:
                if screening_criteria_available:
                    # record criteria
                    pass
                screen_record.screen(
                    review_manager=screen_operation.review_manager,
                    screen_inclusion=True,
                    screening_criteria="...",
                )

            else:
                if screening_criteria_available:
                    # record criteria
                    pass
                screen_record.screen(
                    review_manager=screen_operation.review_manager,
                    screen_inclusion=False,
                    screening_criteria="...",
                )

        screen_operation.review_manager.dataset.save_records_dict(records=records)
        screen_operation.review_manager.dataset.add_record_changes()
        screen_operation.review_manager.create_commit(
            msg="Screen (random)", manual_author=False, script_call="colrev screen"
        )
        return records