#!/usr/bin/env python
import os
import shutil
import typing
from dataclasses import asdict
from pathlib import Path

import git
import pytest
from pybtex.database.input import bibtex

import colrev.env.utils
import colrev.review_manager
import colrev.settings

# Note : the following produces different relative paths locally/on github.
# Path(colrev.__file__).parents[1]

test_data_path = Path()


@pytest.fixture(scope="module")
def review_manager(session_mocker, tmp_path_factory: Path, request) -> colrev.review_manager.ReviewManager:  # type: ignore
    test_repo_dir = tmp_path_factory.mktemp("test_repo")  # type: ignore
    env_dir = tmp_path_factory.mktemp("test_repo")  # type: ignore

    os.chdir(test_repo_dir)
    global test_data_path
    test_data_path = Path(request.fspath).parents[1] / Path("data")

    session_mocker.patch(
        "colrev.env.environment_manager.EnvironmentManager.get_name_mail_from_git",
        return_value=("Tester Name", "tester@email.de"),
    )

    def load_test_records(test_data_path) -> dict:  # type: ignore
        test_records_dict: typing.Dict[Path, dict] = {}
        bib_files_to_index = test_data_path / Path("local_index")
        for file_path in bib_files_to_index.glob("**/*"):
            test_records_dict[Path(file_path.name)] = {}

        for path in test_records_dict.keys():
            with open(bib_files_to_index.joinpath(path), encoding="utf-8") as file:
                parser = bibtex.Parser()
                bib_data = parser.parse_string(file.read())
                test_records_dict[path] = colrev.dataset.Dataset.parse_records_dict(
                    records_dict=bib_data.entries
                )
        return test_records_dict

    temp_sqlite = env_dir / Path("sqlite_index_test.db")
    with session_mocker.patch.object(
        colrev.env.local_index.LocalIndex, "SQLITE_PATH", temp_sqlite
    ):
        test_records_dict = load_test_records(test_data_path)
        local_index = colrev.env.local_index.LocalIndex(verbose_mode=True)
        local_index.reinitialize_sqlite_db()

        for path, records in test_records_dict.items():
            if "cura" in str(path):
                continue
            local_index.index_records(
                records=records,
                repo_source_path=path,
                curated_fields=[],
                curation_url="gh...",
                curated_masterdata=True,
            )

        for path, records in test_records_dict.items():
            if "cura" not in str(path):
                continue
            local_index.index_records(
                records=records,
                repo_source_path=path,
                curated_fields=["literature_review"],
                curation_url="gh...",
                curated_masterdata=False,
            )

    review_manager = colrev.review_manager.ReviewManager(
        path_str=str(test_repo_dir), force_mode=True
    )
    review_manager.settings = colrev.settings.load_settings(
        settings_path=test_data_path.parents[1]
        / Path("colrev/template/init/settings.json")
    )

    review_manager.get_init_operation(
        review_type="literature_review",
        example=False,
    )

    # Note: the strategy is to test the workflow and the endpoints separately
    # We therefore deactivate the (most time consuming endpoints) in the following
    review_manager = colrev.review_manager.ReviewManager(
        path_str=str(review_manager.path)
    )

    example_records_file = test_data_path / Path("search_files/test_records.bib")
    shutil.copy(
        example_records_file, review_manager.path / Path("data/search/test_records.bib")
    )

    review_manager.dataset.add_changes(path=Path("data/search/test_records.bib"))
    review_manager.settings.prep.prep_rounds[0].prep_package_endpoints = [
        {"endpoint": "colrev_built_in.resolve_crossrefs"},
        {"endpoint": "colrev_built_in.source_specific_prep"},
        {"endpoint": "colrev_built_in.exclude_non_latin_alphabets"},
        {"endpoint": "colrev_built_in.exclude_collections"},
    ]
    review_manager.settings.dedupe.dedupe_package_endpoints = [
        {"endpoint": "colrev_built_in.simple_dedupe"}
    ]

    review_manager.settings.pdf_get.pdf_get_package_endpoints = [
        {"endpoint": "colrev_built_in.local_index"}
    ]
    review_manager.settings.pdf_prep.pdf_prep_package_endpoints = []
    review_manager.settings.data.data_package_endpoints = []
    review_manager.save_settings()
    return review_manager


def test_load(review_manager: colrev.review_manager.ReviewManager) -> None:
    load_operation = review_manager.get_load_operation()
    new_sources = load_operation.get_new_sources(skip_query=True)
    load_operation.main(new_sources=new_sources, keep_ids=False, combine_commits=False)


def test_load_pubmed(review_manager: colrev.review_manager.ReviewManager) -> None:
    current_commit = review_manager.dataset.get_last_commit_sha()
    pubmed_file = test_data_path / Path("search_files/pubmed-chatbot.csv")
    shutil.copy(
        pubmed_file, review_manager.path / Path("data/search/pubmed-chatbot.csv")
    )
    load_operation = review_manager.get_load_operation()
    new_sources = load_operation.get_new_sources(skip_query=True)
    new_sources[0].endpoint = "colrev_built_in.pubmed"
    load_operation.main(new_sources=new_sources, keep_ids=False, combine_commits=False)

    expected = (
        test_data_path / Path("search_files/pubmed-chatbot-expected.bib")
    ).read_text()
    actual = (review_manager.path / Path("data/search/pubmed-chatbot.bib")).read_text()
    assert expected == actual
    repo = git.Repo(review_manager.path)

    repo.head.reset(current_commit, index=True, working_tree=True)

    review_manager.load_settings()


def test_prep(review_manager: colrev.review_manager.ReviewManager) -> None:
    prep_operation = review_manager.get_prep_operation()
    prep_operation.main(keep_ids=False)


def test_search(review_manager: colrev.review_manager.ReviewManager) -> None:
    search_operation = review_manager.get_search_operation()
    search_operation.main(rerun=True)

    search_operation.view_sources()


def test_search_get_unique_filename(
    review_manager: colrev.review_manager.ReviewManager,
) -> None:
    search_operation = review_manager.get_search_operation()
    expected = Path("data/search/test_records_1.bib")
    actual = search_operation.get_unique_filename(file_path_string="test_records.bib")
    print(actual)
    assert expected == actual


def test_dedupe(review_manager: colrev.review_manager.ReviewManager) -> None:
    dedupe_operation = review_manager.get_dedupe_operation(
        notify_state_transition_operation=True
    )
    dedupe_operation.main()


def test_prescreen(review_manager: colrev.review_manager.ReviewManager) -> None:
    prescreen_operation = review_manager.get_prescreen_operation()
    prescreen_operation.include_all_in_prescreen(persist=False)


def test_pdf_get(review_manager: colrev.review_manager.ReviewManager) -> None:
    pdf_get_operation = review_manager.get_pdf_get_operation(
        notify_state_transition_operation=True
    )
    pdf_get_operation.main()


def test_pdf_prep(review_manager: colrev.review_manager.ReviewManager) -> None:
    pdf_prep_operation = review_manager.get_pdf_prep_operation(reprocess=False)
    pdf_prep_operation.main(batch_size=0)


def test_pdf_discard(review_manager: colrev.review_manager.ReviewManager) -> None:
    pdf_get_man_operation = review_manager.get_pdf_get_man_operation()
    pdf_get_man_operation.discard()


def test_pdf_prep_man(review_manager: colrev.review_manager.ReviewManager) -> None:
    pdf_prep_man_operation = review_manager.get_pdf_prep_man_operation()
    pdf_prep_man_operation.discard()


def test_screen(review_manager: colrev.review_manager.ReviewManager) -> None:
    screen_operation = review_manager.get_screen_operation()
    screen_operation.include_all_in_screen(persist=False)


def test_data(review_manager: colrev.review_manager.ReviewManager) -> None:
    data_operation = review_manager.get_data_operation()
    data_operation.main()
    review_manager.create_commit(msg="Data and synthesis", manual_author=True)


def test_checks(review_manager: colrev.review_manager.ReviewManager) -> None:
    checker = colrev.checker.Checker(review_manager=review_manager)

    expected = ["0.7.1", "0.7.1"]
    actual = checker.get_colrev_versions()
    assert expected == actual

    checker.check_repository_setup()

    assert False == checker.in_virtualenv()
    expected = []
    actual = checker.check_repo_extended()
    assert expected == actual

    expected = {"status": 0, "msg": "Everything ok."}  # type: ignore
    actual = checker.check_repo()  # type: ignore
    assert expected == actual

    expected = []
    actual = checker.check_repo_basics()
    assert expected == actual

    expected = []
    actual = checker.check_change_in_propagated_id(
        prior_id="Srivastava2015",
        new_id="Srivastava2015a",
        project_context=review_manager.path,
    )
    assert expected == actual

    review_manager.get_search_sources()
    expected = [  # type: ignore
        {  # type: ignore
            "endpoint": "colrev_built_in.pdfs_dir",
            "filename": Path("data/search/pdfs.bib"),
            "search_type": colrev.settings.SearchType.PDFS,
            "search_parameters": {"scope": {"path": "data/pdfs"}},
            "load_conversion_package_endpoint": {"endpoint": "colrev_built_in.bibtex"},
            "comment": "",
        },
        {  # type: ignore
            "endpoint": "colrev_built_in.unknown_source",
            "filename": Path("data/search/test_records.bib"),
            "search_type": colrev.settings.SearchType.DB,
            "search_parameters": {},
            "load_conversion_package_endpoint": {"endpoint": "colrev_built_in.bibtex"},
            "comment": None,
        },
    ]
    search_sources = review_manager.settings.sources
    actual = [asdict(s) for s in search_sources]  # type: ignore
    assert expected == actual