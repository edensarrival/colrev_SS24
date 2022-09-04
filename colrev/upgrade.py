#!/usr/bin/env python3
from __future__ import annotations

import json
import pkgutil
import typing
from pathlib import Path
from typing import TYPE_CHECKING

import git
import pandas as pd
import yaml

if TYPE_CHECKING:
    import colrev.review_manager.ReviewManager


class Upgrade:
    def __init__(
        self,
        *,
        review_manager: colrev.review_manager.ReviewManager,
    ) -> None:

        self.review_manager = review_manager

        last_version, current_version = self.review_manager.get_colrev_versions()

        if "+" in last_version:
            last_version = last_version[: last_version.find("+")]
        if "+" in current_version:
            current_version = current_version[: current_version.find("+")]

        cur_major = current_version[: current_version.rfind(".")]
        next_minor = str(int(current_version[current_version.rfind(".") + 1 :]) + 1)
        upcoming_version = cur_major + "." + next_minor

        colrev.process.CheckProcess(review_manager=self)  # to notify

        def print_release_notes(selected_version: str) -> None:

            filedata = pkgutil.get_data(__name__, "../CHANGELOG.md")
            active = False
            if filedata:
                for line in filedata.decode("utf-8").split("\n"):
                    if selected_version in line:
                        active = True
                        print(f"Release notes v{selected_version}")
                        continue
                    if "### [" in line and selected_version not in line:
                        active = False
                    if active:
                        print(line)

        def migrate_0_4_0(self) -> bool:

            if not Path("settings.json").is_file():
                filedata = pkgutil.get_data(__name__, "template/settings.json")
                if not filedata:
                    print("error reading file")
                    return False
                settings = json.loads(filedata.decode("utf-8"))
            else:
                with open("settings.json", encoding="utf-8") as file:
                    settings = json.load(file)

            old_sources_path = Path("sources.yaml")
            if old_sources_path.is_file():
                if old_sources_path.is_file():
                    with open(old_sources_path, encoding="utf-8") as file:
                        sources_df = pd.json_normalize(yaml.safe_load(file))
                        sources = sources_df.to_dict("records")
                        print(sources)
                for source in sources:
                    if len(source["search_parameters"]) > 0:
                        if "dblp" == source["search_parameters"][0]["endpoint"]:
                            source["source_identifier"] = "{{dblp_key}}"
                        elif "crossref" == source["search_parameters"][0]["endpoint"]:
                            source[
                                "source_identifier"
                            ] = "https://api.crossref.org/works/{{doi}}"
                        elif (
                            "pdfs_directory"
                            == source["search_parameters"][0]["endpoint"]
                        ):
                            source["source_identifier"] = "{{file}}"
                        else:
                            source["source_identifier"] = source["search_parameters"][
                                0
                            ]["endpoint"]

                        source["search_parameters"] = source["search_parameters"][0][
                            "params"
                        ]
                    else:
                        source["search_parameters"] = ""
                        source["source_identifier"] = source.get("source_url", "")

                    if (
                        source["comment"] != source["comment"]
                        or "NA" == source["comment"]
                    ):  # NaN
                        source["comment"] = ""

                    if "source_url" in source:
                        del source["source_url"]
                    if "source_name" in source:
                        del source["source_name"]
                    if "last_sync" in source:
                        del source["last_sync"]

                settings["search"]["sources"] = sources

            if any(r["name"] == "exclusion" for r in settings["prep"]["prep_rounds"]):
                e_r = [
                    r
                    for r in settings["prep"]["prep_rounds"]
                    if r["name"] == "exclusion"
                ][0]
                if "exclude_predatory_journals" in e_r["scripts"]:
                    e_r["scripts"].remove("exclude_predatory_journals")

            for source in settings["search"]["sources"]:
                source["script"] = {"endpoint": "bib_pybtex"}

            settings["prep"]["man_prep_scripts"] = [{"endpoint": "colrev_cli_man_prep"}]
            settings["prescreen"]["scope"] = [{"LanguageScope": ["eng"]}]
            if "plugin" in settings["prescreen"]:
                del settings["prescreen"]["plugin"]
            if "mode" in settings["prescreen"]:
                del settings["prescreen"]["mode"]
            settings["prescreen"]["scripts"] = [
                {"endpoint": "scope_prescreen"},
                {"endpoint": "colrev_cli_prescreen"},
            ]
            if "process" in settings["screen"]:
                del settings["screen"]["process"]
            settings["screen"]["scripts"] = [{"endpoint": "colrev_cli_screen"}]

            settings["pdf_get"]["man_pdf_get_scripts"] = [
                {"endpoint": "colrev_cli_pdf_get_man"}
            ]
            settings["pdf_get"]["scripts"] = [
                {"endpoint": "unpaywall"},
                {"endpoint": "local_index"},
            ]

            settings["pdf_prep"]["scripts"] = [
                {"endpoint": "pdf_check_ocr"},
                {"endpoint": "remove_coverpage"},
                {"endpoint": "remove_last_page"},
                {"endpoint": "validate_pdf_metadata"},
                {"endpoint": "validate_completeness"},
            ]
            settings["pdf_prep"]["man_pdf_prep_scripts"] = [
                {"endpoint": "colrev_cli_pdf_prep_man"}
            ]

            for data_script in settings["data"]["data_format"]:
                if "MANUSCRIPT" == data_script["endpoint"]:
                    if "paper_endpoint_version" not in data_script:
                        data_script["paper_endpoint_version"] = "0.1"
                if "STRUCTURED" == data_script["endpoint"]:
                    if "structured_data_endpoint_version" not in data_script:
                        data_script["structured_data_endpoint_version"] = "0.1"

            if "curated_metadata" in str(self.review_manager.path):
                repo = git.Repo(str(self.review_manager.path))
                settings["project"]["curation_url"] = repo.remote().url.replace(
                    ".git", ""
                )

            if old_sources_path.is_file():
                old_sources_path.unlink()
                self.review_manager.dataset.remove_file_from_git(
                    path=str(old_sources_path)
                )

            if Path("shared_config.ini").is_file():
                Path("shared_config.ini").unlink()
                self.review_manager.dataset.remove_file_from_git(
                    path="shared_config.ini"
                )
            if Path("private_config.ini").is_file():
                Path("private_config.ini").unlink()

            if "curated_metadata" in str(self.review_manager.path):
                settings["project"]["curated_master_data"] = True
                settings["project"]["curated_fields"] = [
                    "doi",
                    "url",
                    "dblp_key",
                ]

            settings["dedupe"]["same_source_merges"] = "prevent"

            if settings["project"]["review_type"] == "NA":
                if "curated_metadata" in str(self.review_manager.path):
                    settings["project"]["review_type"] = "curated_master_data"
                else:
                    settings["project"]["review_type"] = "literature_review"

            with open("settings.json", "w", encoding="utf-8") as outfile:
                json.dump(settings, outfile, indent=4)

            self.review_manager.settings = self.review_manager.load_settings()
            self.review_manager.save_settings()

            self.review_manager.dataset.add_setting_changes()
            records = self.review_manager.dataset.load_records_dict()
            if len(records.values()) > 0:
                for record in records.values():
                    if "manual_duplicate" in record:
                        del record["manual_duplicate"]
                    if "manual_non_duplicate" in record:
                        del record["manual_non_duplicate"]
                    if "origin" in record:
                        record["colrev_origin"] = record["origin"]
                        del record["origin"]
                    if "status" in record:
                        record["colrev_status"] = record["status"]
                        del record["status"]
                    if "excl_criteria" in record:
                        record["exclusion_criteria"] = record["excl_criteria"]
                        del record["excl_criteria"]
                    if "metadata_source" in record:
                        del record["metadata_source"]

                    if "colrev_masterdata" in record:
                        if record["colrev_masterdata"] == "ORIGINAL":
                            del record["colrev_masterdata"]
                        else:
                            record["colrev_masterdata_provenance"] = record[
                                "colrev_masterdata"
                            ]
                            del record["colrev_masterdata"]

                    if "curated_metadata" in str(self.review_manager.path):
                        if "colrev_masterdata_provenance" in record:
                            if "CURATED" == record["colrev_masterdata_provenance"]:
                                record["colrev_masterdata_provenance"] = {}
                    if "colrev_masterdata_provenance" not in record:
                        record["colrev_masterdata_provenance"] = {}
                    if "colrev_data_provenance" not in record:
                        record["colrev_data_provenance"] = {}

                    # if "source_url" in record:
                    #     record["colrev_masterdata"] = \
                    #           "CURATED:" + record["source_url"]
                    #     del record["source_url"]
                    # else:
                    #     record["colrev_masterdata"] = "ORIGINAL"
                    # Note : for curated repositories
                    # record["colrev_masterdata"] = "CURATED"

                self.review_manager.dataset.save_records_dict(records=records)
                self.review_manager.dataset.add_record_changes()

            self.review_manager.retrieve_package_file(
                template_file=Path("template/.pre-commit-config.yaml"),
                target=Path(".pre-commit-config.yaml"),
            )

            self.review_manager.dataset.add_changes(path=".pre-commit-config.yaml")
            # Note: the order is important in this case.
            self.review_manager.dataset.update_colrev_ids()

            return True

        def migrate_0_5_0(self) -> None:

            with open("settings.json", encoding="utf-8") as file:
                settings = json.load(file)

            settings["pdf_get"]["scripts"] = [
                s
                for s in settings["pdf_get"]["scripts"]
                if s["endpoint"] != "website_screenshot"
            ]
            if "sources" in settings["search"]:
                for source in settings["search"]["sources"]:
                    source["script"] = {"endpoint": "bib_pybtex"}
                    if "search" not in source["filename"]:
                        source["filename"] = "search/" + source["filename"]

                if "sources" not in settings:
                    settings["sources"] = settings["search"]["sources"]
                    del settings["search"]["sources"]

                    for source in settings["sources"]:
                        source["search_script"] = source["script"]
                        del source["script"]

                        source["conversion_script"] = {"endpoint": "bibtex"}

                        source["source_prep_scripts"] = []
                        if "CROSSREF" == source["source_name"]:
                            source["search_script"] = {"endpoint": "search_crossref"}
                        if "DBLP" == source["source_name"]:
                            source["search_script"] = {"endpoint": "search_dblp"}
                        if "BACKWARD_SEARCH" == source["source_name"]:
                            source["search_script"] = {"endpoint": "backward_search"}
                        if "COLREV_PROJECT" == source["source_name"]:
                            source["search_script"] = {
                                "endpoint": "search_colrev_project"
                            }
                        if "INDEX" == source["source_name"]:
                            source["search_script"] = {"endpoint": "search_local_index"}
                        if "PDFs" == source["source_name"]:
                            source["search_script"] = {"endpoint": "search_pdfs_dir"}
                        if "bib_pybtex" == source["search_script"]["endpoint"]:
                            source["search_script"] = {}

                settings = {
                    "project": settings["project"],
                    "sources": settings["sources"],
                    "search": settings["search"],
                    "load": settings["load"],
                    "prep": settings["prep"],
                    "dedupe": settings["dedupe"],
                    "prescreen": settings["prescreen"],
                    "pdf_get": settings["pdf_get"],
                    "pdf_prep": settings["pdf_prep"],
                    "screen": settings["screen"],
                    "data": settings["data"],
                }

            if "THREE_AUTHORS_YEAR" == settings["project"]["id_pattern"]:
                settings["project"]["id_pattern"] = "three_authors_year"

            for source in settings["sources"]:
                if "FEED" == source["search_type"]:
                    if "CROSSREF" == source["source_name"]:
                        source["search_type"] = "DB"
                    elif "DBLP" == source["source_name"]:
                        source["search_type"] = "DB"
                    elif "pdfs" == source["source_name"].lower():
                        source["search_type"] = "PDFS"
                    else:
                        source["search_type"] = "DB"

            for prep_round in settings["prep"]["prep_rounds"]:
                prep_round["scripts"] = [
                    s
                    for s in prep_round["scripts"]
                    if s["endpoint"]
                    not in ["get_doi_from_sem_scholar", "update_metadata_status"]
                ]

            if "retrieve_forthcoming" not in settings["search"]:
                if "colrev/curated_metadata" in str(self.review_manager.path):
                    settings["search"]["retrieve_forthcoming"] = False
                else:
                    settings["search"]["retrieve_forthcoming"] = True

            if settings["project"]["review_type"] == "NA":
                if "curated_metadata" in str(self.review_manager.path):
                    settings["project"]["review_type"] = "curated_master_data"
                else:
                    settings["project"]["review_type"] = "literature_review"

            for prep_round in settings["prep"]["prep_rounds"]:
                prep_round["scripts"] = [
                    {"endpoint": s} if "endpoint" not in s and isinstance(str, s) else s
                    for s in prep_round["scripts"]
                ]
            if "explanation" not in settings["prescreen"]:
                settings["prescreen"]["explanation"] = ""
            if "scope" in settings["prescreen"]:
                scope_items = settings["prescreen"]["scope"]
                del settings["prescreen"]["scope"]

                if len(scope_items) > 0:

                    if "scope_prescreen" not in [
                        s["endpoint"] for s in settings["prescreen"]["scripts"]
                    ]:
                        settings["prescreen"].insert(0, {"endpoint": "scope_prescreen"})
                    scope_prescreen = [
                        s
                        for s in settings["prescreen"]["scripts"]
                        if s["endpoint"] == "scope_prescreen"
                    ][0]
                    for elements in scope_items:
                        for scope_key, scope_item in elements.items():
                            scope_prescreen[scope_key] = scope_item

            if settings["screen"]["criteria"] == []:
                settings["screen"]["criteria"] = {}

            if "scripts" not in settings["dedupe"]:
                settings["dedupe"]["scripts"] = [
                    {"endpoint": "active_learning_training"},
                    {
                        "endpoint": "active_learning_automated",
                        "merge_threshold": 0.8,
                        "partition_threshold": 0.5,
                    },
                ]

            if "rename_pdfs" not in settings["pdf_get"]:
                settings["pdf_get"]["rename_pdfs"] = True

            settings["pdf_get"]["man_pdf_get_scripts"] = [
                {"endpoint": "colrev_cli_pdf_get_man"}
            ]
            if "pdf_required_for_screen_and_synthesis" not in settings["pdf_get"]:
                settings["pdf_get"]["pdf_required_for_screen_and_synthesis"] = True

            settings["pdf_prep"]["man_pdf_prep_scripts"] = [
                {"endpoint": "colrev_cli_pdf_prep_man"}
            ]

            if "data_format" in settings["data"]:
                data_scripts = settings["data"]["data_format"]
                del settings["data"]["data_format"]
                settings["data"]["scripts"] = data_scripts

            with open("settings.json", "w", encoding="utf-8") as outfile:
                json.dump(settings, outfile, indent=4)

            self.review_manager.settings = self.review_manager.load_settings()
            self.review_manager.save_settings()
            self.review_manager.dataset.add_setting_changes()

            records = self.review_manager.dataset.load_records_dict()
            if len(records.values()) > 0:
                for record in records.values():
                    if "exclusion_criteria" in record:
                        record["screening_criteria"] = (
                            record["exclusion_criteria"]
                            .replace("=no", "=in")
                            .replace("=yes", "=out")
                        )
                        del record["exclusion_criteria"]

                self.review_manager.dataset.save_records_dict(records=records)
                self.review_manager.dataset.add_record_changes()

            print("Manual steps required to rename references.bib > records.bib.")

            # git branch backup
            # git filter-branch --tree-filter 'if [ -f references.bib ];
            # then mv references.bib records.bib; fi' HEAD
            # rm -d -r .git/refs/original
            # # DO NOT REPLACE IN SETTINGS.json (or in records.bib/references.bib/...)
            # (some search sources may be named "references.bib")
            # git filter-branch --tree-filter
            # "find . \( -name **.md -o -name .pre-commit-config.yaml \)
            # -exec sed -i -e \ 's/references.bib/records.bib/g' {} \;"

        # next version should be:
        # ...
        # {'from': '0.4.0', "to": '0.5.0', 'script': migrate_0_4_0}
        # {'from': '0.5.0', "to": upcoming_version, 'script': migrate_0_5_0}
        migration_scripts: typing.List[typing.Dict[str, typing.Any]] = [
            {"from": "0.4.0", "to": "0.5.0", "script": migrate_0_4_0},
            {"from": "0.5.0", "to": upcoming_version, "script": migrate_0_5_0},
        ]

        # Start with the first step if the version is older:
        if last_version not in [x["from"] for x in migration_scripts]:
            last_version = "0.4.0"

        while current_version in [x["from"] for x in migration_scripts]:
            self.review_manager.logger.info("Current CoLRev version: %s", last_version)

            migrator = [x for x in migration_scripts if x["from"] == last_version].pop()

            migration_script = migrator["script"]

            self.review_manager.logger.info(
                "Migrating from %s to %s", migrator["from"], migrator["to"]
            )

            updated = migration_script(self)
            if updated:
                self.review_manager.logger.info("Updated to: %s", last_version)
            else:
                self.review_manager.logger.info("Nothing to do.")
                self.review_manager.logger.info(
                    "If the update notification occurs again, run\n "
                    "git commit -n -m --allow-empty 'update colrev'"
                )

            # Note : the version in the commit message will be set to
            # the current_version immediately. Therefore, use the migrator['to'] field.
            last_version = migrator["to"]

            if last_version == upcoming_version:
                break

        if self.review_manager.dataset.has_changes():
            self.review_manager.create_commit(
                msg=f"Upgrade to CoLRev {upcoming_version}",
                script_call="colrev settings -u",
            )
            print_release_notes(selected_version=upcoming_version)
        else:
            self.review_manager.logger.info("Nothing to do.")
            self.review_manager.logger.info(
                "If the update notification occurs again, run\n "
                "git commit -n -m --allow-empty 'update colrev'"
            )


if __name__ == "__main__":
    pass
