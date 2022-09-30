#! /usr/bin/env python
"""CoLRev pdf_get operation: Get PDF documents."""
from __future__ import annotations

import os
import shutil
import typing
from glob import glob
from pathlib import Path

from p_tqdm import p_map

import colrev.operation
import colrev.record
import colrev.ui_cli.cli_colors as colors


class PDFGet(colrev.operation.Operation):

    to_retrieve: int
    retrieved: int
    not_retrieved: int

    def __init__(
        self,
        *,
        review_manager: colrev.review_manager.ReviewManager,
        notify_state_transition_operation: bool = True,
    ) -> None:

        super().__init__(
            review_manager=review_manager,
            operations_type=colrev.operation.OperationsType.pdf_get,
            notify_state_transition_operation=notify_state_transition_operation,
        )

        self.cpus = 4
        self.verbose = False

        self.review_manager.pdf_dir.mkdir(exist_ok=True)

        package_manager = self.review_manager.get_package_manager()
        self.pdf_get_package_endpoints: dict[
            str, typing.Any
        ] = package_manager.load_packages(
            package_type=colrev.env.package_manager.PackageEndpointType.pdf_get,
            selected_packages=review_manager.settings.pdf_get.pdf_get_package_endpoints,
            operation=self,
        )

    def copy_pdfs_to_repo(self) -> None:
        self.review_manager.logger.info("Copy PDFs to dir")
        records = self.review_manager.dataset.load_records_dict()

        for record in records.values():
            if "file" in record:
                fpath = Path(record["file"])
                new_fpath = fpath.absolute()
                if fpath.is_symlink():
                    linked_file = fpath.resolve()
                    if linked_file.is_file():
                        fpath.unlink()
                        shutil.copyfile(linked_file, new_fpath)
                        self.review_manager.logger.info(f'Copied PDF ({record["ID"]})')
                elif new_fpath.is_file():
                    self.review_manager.logger.warning(
                        f'No need to copy PDF - already exits ({record["ID"]})'
                    )

    def link_pdf(self, *, record: colrev.record.Record) -> colrev.record.Record:

        pdf_filepath = self.review_manager.PDF_DIR_RELATIVE / Path(
            f"{record.data['ID']}.pdf"
        )
        if pdf_filepath.is_file() and str(pdf_filepath) != record.data.get(
            "file", "NA"
        ):
            record.data.update(file=str(pdf_filepath))

        return record

    # Note : no named arguments (multiprocessing)
    def get_pdf(self, item: dict) -> dict:

        record_dict = item["record"]

        if str(colrev.record.RecordState.rev_prescreen_included) != str(
            record_dict["colrev_status"]
        ):
            return record_dict

        record = colrev.record.Record(data=record_dict)

        record = self.link_pdf(record=record)

        for (
            pdf_get_package_endpoint
        ) in self.review_manager.settings.pdf_get.pdf_get_package_endpoints:

            endpoint = self.pdf_get_package_endpoints[
                pdf_get_package_endpoint["endpoint"]
            ]
            self.review_manager.report_logger.info(
                f'{endpoint.settings.endpoint}({record_dict["ID"]}) called'
            )
            endpoint.get_pdf(self, record)

            if "file" in record.data:
                self.review_manager.report_logger.info(
                    f"{endpoint.settings.endpoint}"
                    f'({record_dict["ID"]}): retrieved .../{Path(record_dict["file"]).name}'
                )
                record.data.update(colrev_status=colrev.record.RecordState.pdf_imported)
                break
            record.data.update(
                colrev_status=colrev.record.RecordState.pdf_needs_manual_retrieval
            )

        return record.get_data()

    def __relink_pdf_files(
        self,
        *,
        records: typing.Dict[str, typing.Dict],
    ) -> typing.Dict[str, typing.Dict]:
        # pylint: disable=too-many-branches

        # Relink files in source file
        corresponding_origin: str
        source_records: typing.List[typing.Dict] = []
        for source in self.review_manager.settings.sources:
            if "{{file}}" != source.source_identifier:
                continue

            if not source.filename.is_file():
                continue

            corresponding_origin = str(source.filename)
            with open(source.filename, encoding="utf8") as target_db:
                source_records_dict = self.review_manager.dataset.load_records_dict(
                    load_str=target_db.read()
                )
            source_records = list(source_records_dict.values())

            self.review_manager.logger.info("Calculate colrev_pdf_ids")
            pdf_candidates = {
                pdf_candidate.relative_to(
                    self.review_manager.path
                ): colrev.record.Record.get_colrev_pdf_id(
                    review_manager=self.review_manager, pdf_path=pdf_candidate
                )
                for pdf_candidate in list(self.review_manager.pdf_dir.glob("**/*.pdf"))
            }

            for record in records.values():
                if "file" not in record:
                    continue

                # Note: we check the source_records based on the cpids
                # in the record because cpids are not stored in the source_record
                # (pdf hashes may change after import/preparation)
                source_rec = {}
                if corresponding_origin != "":
                    source_origin_l = [
                        o for o in record["colrev_origin"] if corresponding_origin in o
                    ]
                    if len(source_origin_l) == 1:
                        source_origin = source_origin_l[0]
                        source_origin = source_origin.replace(
                            f"{corresponding_origin}/", ""
                        )
                        source_rec_l = [
                            s for s in source_records if s["ID"] == source_origin
                        ]
                        if len(source_rec_l) == 1:
                            source_rec = source_rec_l[0]

                if source_rec:
                    if (self.review_manager.path / Path(record["file"])).is_file() and (
                        self.review_manager.path / Path(source_rec["file"])
                    ).is_file():
                        continue
                else:
                    if (self.review_manager.path / Path(record["file"])).is_file():
                        continue

                self.review_manager.logger.info(record["ID"])

                for pdf_candidate, cpid in pdf_candidates.items():
                    if record.get("colrev_pdf_id", "") == cpid:
                        record["file"] = str(pdf_candidate)
                        source_rec["file"] = str(pdf_candidate)

                        self.review_manager.logger.info(
                            f"Found and linked PDF: {pdf_candidate}"
                        )
                        break

            if len(source_records) > 0:
                source_records_dict = {r["ID"]: r for r in source_records}
                self.review_manager.dataset.save_records_dict_to_file(
                    records=source_records_dict, save_path=source.filename
                )

            self.review_manager.dataset.add_changes(path=source.filename)

        return records

    def relink_files(self) -> None:

        self.review_manager.logger.info(
            "Checking PDFs in same directory to reassig when the cpid is identical"
        )
        records = self.review_manager.dataset.load_records_dict()
        records = self.__relink_pdf_files(records=records)

        self.review_manager.dataset.save_records_dict(records=records)

        self.review_manager.dataset.add_record_changes()
        self.review_manager.create_commit(
            msg="Relink PDFs", script_call="colrev pdf-get"
        )

    def check_existing_unlinked_pdfs(
        self,
        *,
        records: dict,
    ) -> dict:

        linked_pdfs = [
            str(Path(x["file"]).resolve()) for x in records.values() if "file" in x
        ]

        pdf_files = glob(str(self.review_manager.pdf_dir) + "/**.pdf", recursive=True)
        unlinked_pdfs = [Path(x) for x in pdf_files if x not in linked_pdfs]

        if len(unlinked_pdfs) == 0:
            return records

        grobid_service = self.review_manager.get_grobid_service()
        grobid_service.start()
        self.review_manager.logger.info("Checking unlinked PDFs")
        for file in unlinked_pdfs:
            self.review_manager.logger.info(f"Checking unlinked PDF: {file}")
            if file.stem not in records.keys():

                tei = self.review_manager.get_tei(pdf_path=file)
                pdf_record = tei.get_metadata()

                if "error" in pdf_record:
                    continue

                max_similarity = 0.0
                max_sim_record = None
                for record in records.values():
                    sim = colrev.record.Record.get_record_similarity(
                        record_a=colrev.record.Record(data=pdf_record),
                        record_b=colrev.record.Record(data=record.copy()),
                    )
                    if sim > max_similarity:
                        max_similarity = sim
                        max_sim_record = record
                if max_sim_record:
                    if max_similarity > 0.5:
                        if (
                            colrev.record.RecordState.pdf_prepared
                            == max_sim_record["colrev_status"]
                        ):
                            continue

                        max_sim_record.update(file=str(file))
                        max_sim_record.update(
                            colrev_status=colrev.record.RecordState.pdf_imported
                        )

                        self.review_manager.report_logger.info(
                            "linked unlinked pdf:" f" {file.name}"
                        )
                        self.review_manager.logger.info(
                            "linked unlinked pdf:" f" {file.name}"
                        )
                        # max_sim_record = \
                        #     pdf_prep.validate_pdf_metadata(max_sim_record)
                        # colrev_status = max_sim_record['colrev_status']
                        # if RecordState.pdf_needs_manual_preparation == colrev_status:
                        #     # revert?

        return records

    def rename_pdfs(self) -> None:
        self.review_manager.logger.info("Rename PDFs")

        records = self.review_manager.dataset.load_records_dict()

        # We may use other pdfs_search_files from the sources:
        # review_manager.settings.sources
        pdfs_search_file = Path("data/search/pdfs.bib")

        for record in records.values():
            if "file" not in record:
                continue

            file = Path(record["file"])
            new_filename = file.parents[0] / Path(f"{record['ID']}.pdf")
            # Possible option: move to top (pdfs) directory:
            # new_filename = self.review_manager.PDF_DIR_RELATIVE / Path(
            #     f"{record['ID']}.pdf"
            # )
            if str(file) == str(new_filename):
                continue

            # This should replace the file fields
            colrev.env.utils.inplace_change(
                filename=self.review_manager.dataset.RECORDS_FILE_RELATIVE,
                old_string="{" + str(file) + "}",
                new_string="{" + str(new_filename) + "}",
            )
            # This should replace the provenance dict fields
            colrev.env.utils.inplace_change(
                filename=self.review_manager.dataset.RECORDS_FILE_RELATIVE,
                old_string=":" + str(file) + ";",
                new_string=":" + str(new_filename) + ";",
            )

            if pdfs_search_file.is_file():
                colrev.env.utils.inplace_change(
                    filename=pdfs_search_file,
                    old_string=str(file),
                    new_string=str(new_filename),
                )

            if not file.is_file():
                corrected_path = Path(str(file).replace("  ", " "))
                if corrected_path.is_file():
                    file = corrected_path

            if file.is_file():
                file.rename(new_filename)
            elif file.is_symlink():
                os.rename(str(file), str(new_filename))

            record["file"] = str(new_filename)
            self.review_manager.logger.info(f"rename {file.name} > {new_filename}")

        if pdfs_search_file.is_file():
            self.review_manager.dataset.add_changes(path=pdfs_search_file)
        self.review_manager.dataset.add_record_changes()

    def __get_data(self) -> dict:
        record_state_list = self.review_manager.dataset.get_record_state_list()
        nr_tasks = len(
            [
                x
                for x in record_state_list
                if str(colrev.record.RecordState.rev_prescreen_included)
                == x["colrev_status"]
            ]
        )

        items = self.review_manager.dataset.read_next_record(
            conditions=[
                {"colrev_status": colrev.record.RecordState.rev_prescreen_included}
            ],
        )

        self.to_retrieve = nr_tasks

        pdf_get_data = {
            "nr_tasks": nr_tasks,
            "items": [{"record": item} for item in items],
        }
        self.review_manager.logger.debug(
            self.review_manager.p_printer.pformat(pdf_get_data)
        )

        self.review_manager.logger.debug(
            f"pdf_get_data: {self.review_manager.p_printer.pformat(pdf_get_data)}"
        )

        self.review_manager.logger.debug(
            self.review_manager.p_printer.pformat(pdf_get_data["items"])
        )

        return pdf_get_data

    def _print_stats(self, *, retrieved_record_list: list) -> None:

        self.retrieved = len([r for r in retrieved_record_list if "file" in r])

        self.not_retrieved = self.to_retrieve - self.retrieved

        retrieved_string = "Retrieved: "
        if self.retrieved == 0:
            retrieved_string += f"{self.retrieved}".rjust(11, " ")
            retrieved_string += " PDFs"
        elif self.retrieved == 1:
            retrieved_string += f"{colors.GREEN}"
            retrieved_string += f"{self.retrieved}".rjust(11, " ")
            retrieved_string += f"{colors.END} PDF"
        else:
            retrieved_string += f"{colors.GREEN}"
            retrieved_string += f"{self.retrieved}".rjust(11, " ")
            retrieved_string += f"{colors.END} PDFs"

        not_retrieved_string = "Missing:   "
        if self.not_retrieved == 0:
            not_retrieved_string += f"{self.not_retrieved}".rjust(11, " ")
            not_retrieved_string += " PDFs"
        elif self.not_retrieved == 1:
            not_retrieved_string += f"{colors.ORANGE}"
            not_retrieved_string += f"{self.not_retrieved}".rjust(11, " ")
            not_retrieved_string += f"{colors.END} PDF"
        else:
            not_retrieved_string += f"{colors.ORANGE}"
            not_retrieved_string += f"{self.not_retrieved}".rjust(11, " ")
            not_retrieved_string += f"{colors.END} PDFs"

        self.review_manager.logger.info(retrieved_string)
        self.review_manager.logger.info(not_retrieved_string)

    def __set_status_if_file_linked(self, *, records: dict) -> dict:

        for record in records.values():
            if record["colrev_status"] in [
                colrev.record.RecordState.rev_prescreen_included,
                colrev.record.RecordState.pdf_needs_manual_retrieval,
            ]:
                if "file" in record:
                    if any(
                        Path(fpath).is_file() for fpath in record["file"].split(";")
                    ):
                        record["colrev_status"] = colrev.record.RecordState.pdf_imported
                    else:
                        print(
                            "Warning: record with file field but no existing PDF "
                            f'({record["ID"]}: {record["file"]}'
                        )
        self.review_manager.dataset.save_records_dict(records=records)
        self.review_manager.dataset.add_record_changes()

        return records

    def setup_custom_script(self) -> None:

        filedata = colrev.env.utils.get_package_file_content(
            file_path=Path("template/custom_pdf_get_script.py")
        )
        if filedata:
            with open("custom_pdf_get_script.py", "w", encoding="utf-8") as file:
                file.write(filedata.decode("utf-8"))

        self.review_manager.dataset.add_changes(path=Path("custom_pdf_get_script.py"))

        self.review_manager.settings.pdf_get.pdf_get_man_package_endpoints.append(
            {"endpoint": "custom_pdf_get_script"}
        )

        self.review_manager.save_settings()

    def main(self) -> None:

        saved_args = locals()

        self.review_manager.report_logger.info("Get PDFs")
        self.review_manager.logger.info("Get PDFs")

        records = self.review_manager.dataset.load_records_dict()
        records = self.__set_status_if_file_linked(records=records)
        records = self.check_existing_unlinked_pdfs(records=records)

        pdf_get_data = self.__get_data()

        if pdf_get_data["nr_tasks"] > 0:

            retrieved_record_list = p_map(self.get_pdf, pdf_get_data["items"])

            self.review_manager.dataset.save_record_list_by_id(
                record_list=retrieved_record_list
            )

            # Note: rename should be after copy.
            # Note : do not pass records as an argument.
            if self.review_manager.settings.pdf_get.rename_pdfs:
                self.rename_pdfs()

            self._print_stats(retrieved_record_list=retrieved_record_list)
        else:
            self.review_manager.logger.info("No additional pdfs to retrieve")

            # Note: rename should be after copy.
            # Note : do not pass records as an argument.
            if self.review_manager.settings.pdf_get.rename_pdfs:
                self.rename_pdfs()

        self.review_manager.create_commit(
            msg="Get PDFs", script_call="colrev pdf-get", saved_args=saved_args
        )


if __name__ == "__main__":
    pass