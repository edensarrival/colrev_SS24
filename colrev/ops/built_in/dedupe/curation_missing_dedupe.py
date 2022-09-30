#! /usr/bin/env python
"""Deduplication of remaining records in curated metadata repositories"""
from __future__ import annotations

import typing
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import zope.interface
from dacite import from_dict
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.ops.built_in.pdf_prep.metadata_valiation
import colrev.record
import colrev.ui_cli.cli_colors as colors

if TYPE_CHECKING:
    import colrev.ops.dedupe

# pylint: disable=too-many-arguments
# pylint: disable=too-few-public-methods
# pylint: disable=duplicate-code


@zope.interface.implementer(colrev.env.package_manager.DedupePackageInterface)
@dataclass
class CurationMissingDedupe(JsonSchemaMixin):
    """Deduplication of remaining records in a curated metadata repository"""

    settings_class = colrev.env.package_manager.DefaultSettings

    def __init__(
        self,
        *,
        dedupe_operation: colrev.ops.dedupe.Dedupe,  # pylint: disable=unused-argument
        settings: dict,
    ):
        self.settings = from_dict(data_class=self.settings_class, data=settings)

    def __create_dedupe_source_stats(
        self, *, dedupe_operation: colrev.ops.dedupe.Dedupe
    ) -> None:
        # Note : reload to generate correct statistics

        Path("dedupe").mkdir(exist_ok=True)

        source_origins = [
            str(source.filename).replace("data/search/", "")
            for source in dedupe_operation.review_manager.settings.sources
        ]

        records = dedupe_operation.review_manager.dataset.load_records_dict()
        for source_origin in source_origins:

            selected_records = [
                r
                for r in records.values()
                if any(source_origin in co for co in r["colrev_origin"])
                and r["colrev_status"]
                in [
                    colrev.record.RecordState.md_prepared,
                    colrev.record.RecordState.md_needs_manual_preparation,
                    colrev.record.RecordState.md_imported,
                ]
            ]
            records_df = pd.DataFrame.from_records(list(selected_records))
            if records_df.shape[0] == 0:
                dedupe_operation.review_manager.logger.info(
                    f"{colors.GREEN}Source {source_origin} fully merged{colors.END}"
                )
            else:
                dedupe_operation.review_manager.logger.info(
                    f"{colors.ORANGE}Source {source_origin} not fully merged{colors.END}"
                )
                dedupe_operation.review_manager.logger.info(
                    f"Exporting details to dedupe/{source_origin}.xlsx"
                )

                records_df = records_df[
                    records_df.columns.intersection(
                        [
                            "ID",
                            "colrev_status",
                            "journal",
                            "booktitle",
                            "year",
                            "volume",
                            "number",
                            "title",
                            "author",
                        ]
                    )
                ]
                keys = list(
                    records_df.columns.intersection(["year", "volume", "number"])
                )
                if "year" in keys:
                    records_df.year = pd.to_numeric(records_df.year, errors="coerce")
                if "volume" in keys:
                    records_df.volume = pd.to_numeric(
                        records_df.volume, errors="coerce"
                    )
                if "number" in keys:
                    records_df.number = pd.to_numeric(
                        records_df.number, errors="coerce"
                    )
                records_df.sort_values(by=keys, inplace=True)
                records_df.to_excel(f"dedupe/{source_origin}.xlsx", index=False)

    def __process_missing_duplicates(
        self, *, dedupe_operation: colrev.ops.dedupe.Dedupe
    ) -> dict:
        # pylint: disable=too-many-locals
        # pylint: disable=too-many-branches

        records = dedupe_operation.review_manager.dataset.load_records_dict()
        nr_recs_to_merge = len(
            [
                x
                for x in records.values()
                if x["colrev_status"] in [colrev.record.RecordState.md_prepared]
            ]
        )
        nr_recs_checked = 0
        results: typing.Dict[str, list] = {
            "decision_list": [],
            "add_records_to_md_processed_list": [],
            "records_to_prepare": [],
        }

        for record_dict in records.values():
            if record_dict["colrev_status"] not in [
                colrev.record.RecordState.md_prepared
            ]:
                continue
            record = colrev.record.Record(data=record_dict)

            toc_key = record.get_toc_key()
            same_toc_recs = [
                r
                for r in records.values()
                if toc_key == colrev.record.Record(data=r).get_toc_key()
                if r["ID"] != record.data["ID"]
                and r["colrev_status"]
                not in [
                    colrev.record.RecordState.md_prepared,
                    colrev.record.RecordState.md_needs_manual_preparation,
                    colrev.record.RecordState.md_imported,
                ]
            ]

            if len(same_toc_recs) == 0:
                print("no same toc records")
                continue

            print("\n\n\n")
            print(colors.ORANGE)
            record.print_citation_format()
            print(colors.END)

            for same_toc_rec in same_toc_recs:
                same_toc_rec[
                    "similarity"
                ] = colrev.record.PrepRecord.get_record_similarity(
                    record_a=colrev.record.Record(data=same_toc_rec), record_b=record
                )

            same_toc_recs = sorted(
                same_toc_recs, key=lambda d: d["similarity"], reverse=True
            )

            i = 0
            for i, same_toc_rec in enumerate(same_toc_recs):
                author_title_string = (
                    f"{same_toc_rec.get('author', 'NO_AUTHOR')} : "
                    + f"{same_toc_rec.get('title', 'NO_TITLE')}"
                )

                if same_toc_rec["similarity"] > 0.8:
                    print(f"{i + 1} - {colors.ORANGE}{author_title_string}{colors.END}")

                else:
                    print(f"{i + 1} - {author_title_string}")

            valid_selection = False
            quit_pressed = False
            while not valid_selection:
                ret = input(
                    f"({nr_recs_checked}/{nr_recs_to_merge}) "
                    f"Merge with record [{1}...{i+1} / s / a / p / q]?   "
                )
                if "s" == ret:
                    valid_selection = True
                elif "q" == ret:
                    quit_pressed = True
                    valid_selection = True
                elif "a" == ret:
                    results["add_records_to_md_processed_list"].append(
                        record.data["ID"]
                    )
                    valid_selection = True
                elif "p" == ret:
                    results["records_to_prepare"].append(record.data["ID"])
                    valid_selection = True
                elif ret.isdigit():
                    if int(ret) - 1 <= i:
                        results["decision_list"].append(
                            {
                                "ID1": record.data["ID"],
                                "ID2": same_toc_recs[int(ret) - 1]["ID"],
                                "decision": "duplicate",
                            }
                        )

                        valid_selection = True
            nr_recs_checked += 1
            if quit_pressed:
                break
        return results

    def run_dedupe(self, dedupe_operation: colrev.ops.dedupe.Dedupe) -> None:

        # pylint: disable=too-many-branches
        # pylint: disable=too-many-statements

        # export sets of non-merged records
        # (and merged records a different xlsx for easy sort/merge)

        # Note : this script is necessary because the active learning is insufficient:
        # the automated ML-deduplication still has a certain error rate
        # which makes it less useful for curations
        # the active learning labeling presents cases on both sides
        # (likely duplicates and non-duplicates to maximize training quality)
        # For the curation, we are only interested in the duplicate, not the classifier

        print("\n\n")
        print(
            "In the following, "
            "records can be added to the curated (md_processed*) records.\n"
            "Curated records are displayed for the same table-of-content item "
            "(i.e., same year/volume/number)"
        )
        print("\n\n")

        ret = self.__process_missing_duplicates(dedupe_operation=dedupe_operation)

        if len(ret["decision_list"]) > 0:
            print("Duplicates identified:")
            print(ret["decision_list"])
            dedupe_operation.apply_merges(results=ret["decision_list"])

        if len(ret["records_to_prepare"]) > 0:
            records = dedupe_operation.review_manager.dataset.load_records_dict()
            for record_id, record_dict in records.items():
                if record_id in ret["records_to_prepare"]:
                    record = colrev.record.Record(data=record_dict)
                    record.set_status(
                        target_state=colrev.record.RecordState.md_needs_manual_preparation
                    )

            dedupe_operation.review_manager.dataset.save_records_dict(records=records)

        if len(ret["decision_list"]) > 0 or len(ret["records_to_prepare"]) > 0:

            dedupe_operation.review_manager.dataset.add_record_changes()

            dedupe_operation.review_manager.create_commit(
                msg="Merge duplicate records",
                script_call="colrev dedupe",
                saved_args={},
            )

        if len(ret["add_records_to_md_processed_list"]) > 0:
            records = dedupe_operation.review_manager.dataset.load_records_dict()
            for record_id, record_dict in records.items():
                if record_id in ret["add_records_to_md_processed_list"]:
                    if record_dict["colrev_status"] in [
                        colrev.record.RecordState.md_prepared,
                        colrev.record.RecordState.md_needs_manual_preparation,
                        colrev.record.RecordState.md_imported,
                    ]:
                        record = colrev.record.Record(data=record_dict)
                        record.set_status(
                            target_state=colrev.record.RecordState.md_processed
                        )

            dedupe_operation.review_manager.dataset.save_records_dict(records=records)
            dedupe_operation.review_manager.dataset.add_record_changes()

            input("Edit records (if any) and press Enter")

            dedupe_operation.review_manager.dataset.add_record_changes()

            dedupe_operation.review_manager.create_commit(
                msg="Add non-duplicate records",
                script_call="colrev dedupe",
                saved_args={},
            )

        self.__create_dedupe_source_stats(dedupe_operation=dedupe_operation)


if __name__ == "__main__":
    pass