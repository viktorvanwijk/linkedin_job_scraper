# -*- coding: utf-8 -*-
"""
Created on Mon Mar 11 14:16:09 2024

@author: Hans
"""

import os
import sys
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Union, Tuple, Callable

import pandas as pd
from pandas import DataFrame
from PyQt5.QtCore import (
    QAbstractTableModel, QModelIndex, QObject, Qt, QThread, pyqtSignal)
from PyQt5.QtGui import QIcon, QKeyEvent
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QProgressDialog, QPushButton, QSizePolicy, QSpinBox, QTableView, QVBoxLayout,
    QWidget)

import constants as C
from job_scraper import (
    DESCRIPTION_KEYWORDS, TITLE_KEYWORDS_TO_ALWAYS_KEEP,
    TITLE_KEYWORDS_TO_DISCARD, TITLE_KEYWORDS_TO_KEEP, WL, BadStatusCode,
    LinkedinJobScraper, LinkedinSession, filter_job_descriptions,
    filter_job_titles, save_job_dataframe_to_html_file)
from logger import CONN, DEBUG, INFO, logger

logger.setLevel(CONN)

SIZE_FIXED = QSizePolicy.Fixed
SIZE_MIN_EXPANDING = QSizePolicy.MinimumExpanding
SIZE_MIN = QSizePolicy.Minimum

LABEL_ROLE = QFormLayout.LabelRole
FIELD_ROLE = QFormLayout.FieldRole

PATH_ICONS = f"{os.path.dirname(__file__)}\\icons"


class MainWindow(QWidget):
    MIN_WIDTH = 1280
    MIN_HEIGHT = 960

    class BUTTON_GROUPS(Enum):
        AFTER_INIT = ("test_session", "get_n_jobs", "scrape_jobs")
        AFTER_SCRAPE = AFTER_INIT + (
            "filter_job_titles",
            "get_job_descriptions",
            "save_results",
            "reset_table_view"
        )
        AFTER_JOB_DESCR = AFTER_SCRAPE + ("filter_job_descriptions",)
        WHILE_ACTION = ("stop_worker",)

    def __init__(
        self,
        scraper: LinkedinJobScraper,
        save_folder: str,
        *args,
        **kwargs,
    ):
        """

        Parameters
        ----------
        session : LinkedinSession
        scraper : LinkedinJobScraper
        save_folder : str
            Folder to save the results in.
        """
        super().__init__(*args, **kwargs)

        self.scraper: LinkedinJobScraper = scraper
        self.session = scraper.session
        self.worker: Worker = None
        self.save_folder = save_folder

        self._l = logger.getChild(self.__class__.__name__)

        self.df = None
        self.metadata = None

        self._last_button_states: Enum = self.BUTTON_GROUPS.AFTER_INIT
        self._results_saved: bool = None

        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize all UI elements."""
        self.setWindowTitle("LinkedIn Job Scraper")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.setStyleSheet(
            "QPushButton {font: 10pt Times} " "QLabel {font: 10pt Times}"
        )
        self.setWindowIcon(QIcon(f"{PATH_ICONS}/linkedin-icon-filled-64.ico"))

        # Left side widgets
        self.settings_groupbox = QGroupBox("Settings")
        self.settings_groupbox.setSizePolicy(SIZE_MIN_EXPANDING, SIZE_FIXED)

        self.title_filter_groupbox = QGroupBox("Title filter")
        self.title_filter_groupbox.setSizePolicy(SIZE_MIN_EXPANDING, SIZE_FIXED)

        self.description_filter_groupbox = QGroupBox("Description filter")
        self.description_filter_groupbox.setSizePolicy(SIZE_MIN_EXPANDING, SIZE_FIXED)

        self.actions_groupbox = QGroupBox("Actions")
        self.actions_groupbox.setSizePolicy(SIZE_MIN_EXPANDING, SIZE_FIXED)

        self.form_settings_layout = FormSettingsLayout(
            setting_params=(
                C.URL_PARAM_KEYWORDS,
                C.URL_PARAM_N_DAYS,
                C.URL_PARAM_LOCATION,
                C.URL_PARAM_GEO_ID,
            ),
            default_values={
                C.URL_PARAM_N_DAYS: LinkedinJobScraper.N_DAYS,
                C.URL_PARAM_LOCATION: LinkedinJobScraper.LOCATION,
                C.URL_PARAM_GEO_ID: LinkedinJobScraper.GEO_ID,
                C.URL_PARAM_KEYWORDS: "python",
            },
        )
        self.work_location_layout = WorkLocationLayout()
        self.title_filter_layouts = {
            "always_keep": FilterKeywordsLayout(
                "Keywords to always keep", TITLE_KEYWORDS_TO_ALWAYS_KEEP
            ),
            "keep": FilterKeywordsLayout(
                "Keywords to keep", TITLE_KEYWORDS_TO_KEEP
            ),
            "discard": FilterKeywordsLayout(
                "Keywords to discard", TITLE_KEYWORDS_TO_DISCARD
            ),
        }
        self.description_filter_input = FilterKeywordsLayout(
            "Keywords", DESCRIPTION_KEYWORDS
        )
        self.mark_descr_keywords_checkbox = QCheckBox(
            "Mark description keywords"
        )
        self.mark_descr_keywords_checkbox.setChecked(True)
        self.mark_descr_keywords_checkbox.setToolTip(
            "Dictates whether description keywords will be marked in the "
            "results."
        )
        self.buttons = {}
        # fmt: off
        buttons = [
            ("test_session", "Test session", self._callback_test_session, True),
            ("get_n_jobs", "Get number of jobs", self._callback_get_n_jobs, True),
            ("scrape_jobs", "Fetch jobs", self._callback_scrape_jobs, True),
            ("filter_job_titles", "Filter", self._callback_filter_job_titles, False),
            ("get_job_descriptions", "Fetch job descriptions", self._callback_get_job_descriptions, False),
            ("filter_job_descriptions", "Filter", self._callback_filter_job_descriptions, False),
            ("save_results", "Save results", self._callback_save_results, False),
            ("reset_table_view", "Reset filters", self._callback_reset_table_view, False),
            ("stop_worker", "Stop", self._callback_stop_worker, False),
        ]
        for button in buttons:
            self._create_button(*button)
        # fmt: on

        # Right side widgets
        jobs_groupbox = QGroupBox("Jobs")
        self.job_table = JobTableViewer()

        # Add widgets to layout
        layout = QHBoxLayout(self)

        layout_settings = QVBoxLayout(self.settings_groupbox)
        layout_settings.addLayout(self.form_settings_layout)
        layout_settings.addLayout(self.work_location_layout)

        layout_title_filters = QVBoxLayout(self.title_filter_groupbox)
        for tfl in self.title_filter_layouts.values():
            layout_title_filters.addLayout(tfl)
        layout_title_filters.addWidget(self.buttons["filter_job_titles"])

        layout_description_filter = QVBoxLayout(self.description_filter_groupbox)
        layout_description_filter.addLayout(self.description_filter_input)
        layout_description_filter.addWidget(self.mark_descr_keywords_checkbox)
        layout_description_filter.addWidget(self.buttons["filter_job_descriptions"])

        # TODO: where to put the reset_table_view button?
        layout_actions = QVBoxLayout(self.actions_groupbox)
        for button in ("test_session", "get_n_jobs", "scrape_jobs", "get_job_descriptions"):
            layout_actions.addWidget(self.buttons[button])

        layout_l = QVBoxLayout()
        layout_l.addWidget(self.settings_groupbox)
        layout_l.addWidget(self.title_filter_groupbox)
        layout_l.addWidget(self.description_filter_groupbox)
        layout_l.addStretch()
        layout_l.addWidget(self.actions_groupbox)

        layout_jobs_groupbox = QVBoxLayout(jobs_groupbox)
        layout_jobs_groupbox.addWidget(self.job_table)

        layout.addLayout(layout_l)
        layout.addWidget(jobs_groupbox, 1)

    def _callback_test_session(self) -> None:
        """Callback for the 'Test session' (test_session) button."""
        self._lock_buttons()
        try:
            self.session.test_session()
            QMessageBox.information(self, "Test session", "Testing successful.")
        except (SystemError, TimeoutError, BadStatusCode) as e:
            QMessageBox.critical(
                self, "Test session", f"Error during testing of session: {e}"
            )
        self._unlock_buttons(self._last_button_states)

    def _callback_get_n_jobs(self) -> None:
        """Callback for the 'Get number of jobs' (get_n_jobs) button.

        Gets the specified settings and checks them, and only continues if
        they are ok.
        """
        settings_dict = self._get_settings_dict()
        if not self._check_settings_dict(settings_dict):
            return

        self._lock_buttons()
        self.worker = Worker(self.scraper.determine_n_jobs, **settings_dict)
        self.worker.result.connect(self._slot_get_n_jobs)
        self.worker.start()
        self._unlock_buttons(self.BUTTON_GROUPS.WHILE_ACTION)

    def _slot_get_n_jobs(self, n_jobs: int) -> None:
        """Slot for the get number of jobs result."""
        QMessageBox.information(
            self, "Number of jobs", f"Number of jobs: {n_jobs}"
        )
        self._unlock_buttons(self._last_button_states)
        self._lock_buttons(self.BUTTON_GROUPS.WHILE_ACTION)

    def _callback_scrape_jobs(self) -> None:
        """Callback for the 'Fetch jobs' (scrape_jobs) button.

        Gets the specified settings and checks them, and only continues if
        they are ok. If the number of fetched jobs is zero, an information
        message box will be displayed
        """
        if not self._check_continue_results_saved("continue"):
            return

        settings_dict = self._get_settings_dict()
        if not self._check_settings_dict(settings_dict):
            return

        self._lock_buttons()
        self.worker = Worker(
            self.scraper.scrape_jobs, **settings_dict
        )
        self.worker.result.connect(self._slot_scrape_jobs_result)

        self.pd = QProgressDialogWithConfirmation(
            "Fetching jobs...", "Cancel", 0, 100, parent=self
        )
        self.pd.canceled.connect(self._callback_stop_worker)
        self.worker.finished.connect(self.pd.close)
        self.pd.show()

        self.worker.start()
        self._unlock_buttons(self.BUTTON_GROUPS.WHILE_ACTION)

    def _slot_scrape_jobs_result(self, res: Tuple) -> None:
        """Slot for the scraping jobs result."""
        assert isinstance(res, tuple)
        assert isinstance(res[0], DataFrame)
        assert isinstance(res[1], dict)

        self.df, self.metadata = res
        if not self.df.empty:
            self.job_table.display_jobs(self.df)
            QMessageBox.information(
                self, "Fetch jobs", "Job fetching completed"
            )
            self._last_button_states = self.BUTTON_GROUPS.AFTER_SCRAPE
            self._results_saved = False
        else:
            # TODO: this will also be called if LinkedinSession raised a timeout
            #  error, which shouldn't be the case
            QMessageBox.information(
                self, "Fetch jobs", "No jobs available with current settings"
            )
        self._lock_buttons(self.BUTTON_GROUPS.WHILE_ACTION)
        self._unlock_buttons(self._last_button_states)

    def _callback_filter_job_titles(self) -> None:
        """Callback for the 'Filter job titles' (filter_job_titles) button.

        Checks if at least on of the filter text boxes contains keywords.
        Shows a warning message box if not.
        """
        filter_lists = [
            self.title_filter_layouts["always_keep"].get_keyword_list(),
            self.title_filter_layouts["keep"].get_keyword_list(),
            self.title_filter_layouts["discard"].get_keyword_list(),
        ]
        if all(fl is None for fl in filter_lists):
            QMessageBox.warning(
                self, "Settings error", "Please enter some filters"
            )
            return

        self._lock_buttons()
        current_indices = self.job_table.get_current_dataframe_indices()
        df_res = filter_job_titles(self.df, *filter_lists, current_indices)
        self.job_table.display_jobs(df_res)
        self._unlock_buttons(self._last_button_states)

    def _callback_get_job_descriptions(self) -> None:
        """Callback for the 'Fetch job descriptions' (get_job_descriptions)
        button.

        Shows an information message box upon completion.
        """
        self._lock_buttons()
        current_indices = self.job_table.get_current_dataframe_indices()
        self._l.debug(f"Get job descriptions: {current_indices}")
        self.worker = Worker(
            self.scraper.get_job_descriptions, self.df, current_indices
        )
        self.worker.result.connect(self._slot_get_job_descriptions_result)

        # TODO: add progress dialog. Maybe create new method to combine it with
        #  self._callback_scrape_jobs

        self.worker.start()
        self._unlock_buttons(self.BUTTON_GROUPS.WHILE_ACTION)

    def _slot_get_job_descriptions_result(self, res: DataFrame) -> None:
        """Slot for the scraping jobs result."""
        self.job_table.display_jobs(res)
        QMessageBox.information(
            self,
            "Fetch job descriptions",
            "Fetching of job descriptions is completed",
        )
        self._last_button_states = self.BUTTON_GROUPS.AFTER_JOB_DESCR
        self._lock_buttons(self.BUTTON_GROUPS.WHILE_ACTION)
        self._unlock_buttons(self._last_button_states)

    def _callback_filter_job_descriptions(self) -> None:
        """Callback for the 'Filter job descriptions' (filter_job_descriptions)
        button.

        Checks if a description filter was specified. Shows a warning message
        box if not.
        """
        keywords = self.description_filter_input.get_keyword_list()
        if keywords is None:
            QMessageBox.warning(
                self,
                "Filtering job descriptions",
                "Please enter a keyword to filter job descriptions",
            )
            return

        current_indices = self.job_table.get_current_dataframe_indices()
        df_res = filter_job_descriptions(
            self.df, keywords, current_indices, True
        )
        self.job_table.display_jobs(df_res)

    def _callback_save_results(self) -> None:
        """Callback for 'Save results' (save_results) button.

        Only saves the data of the jobs that are currently shown in the table
        view.
        """
        current_indices = self.job_table.get_current_dataframe_indices()
        self._l.info(f"Saving results to: {self.save_folder}")
        save_job_dataframe_to_html_file(
            self.df.loc[current_indices, :],
            self.metadata,
            folder=self.save_folder,
            use_marked_descriptions=self.mark_descr_keywords_checkbox.isChecked(),
        )
        self._results_saved = True
        QMessageBox.information(self, "Saving", "Saving is completed")

    def _callback_reset_table_view(self) -> None:
        """Callback for the 'Reset filters' (reset_table_view) button.

        Removes all applied filters and shows all the jobs that were fetched.
        """
        self.job_table.display_jobs(self.df)

    def _callback_stop_worker(self) -> None:
        """Callback for the 'Stop' (stop_worker) button.

        Stops the current thread worker (if it exists) and resets the buttons
        to their state before the worker was started.

        Should only be used in emergencies.
        """
        if self.worker is None or not self.worker.isRunning():
            return

        # NOTE: normally, threads should be stopped using quit() instead of
        # terminate(). But here, the blocking method with an infinite loop is
        # executed outside the worker class, so using terminate() is the only
        # solution which directly stops the thread.
        # See: https://doc.qt.io/qtforpython-5/PySide2/QtCore/QThread.html
        self.worker.terminate()
        self._lock_buttons(self.BUTTON_GROUPS.WHILE_ACTION)
        self._unlock_buttons(self._last_button_states)

    def _change_button_states(self, button_states: Dict[str, bool]) -> None:
        """Change button states.

        button_states : Dict[str, bool]
            Dictionary of button states with button names as keys and
            states as values.
        """
        for name, state in button_states.items():
            self.buttons[name].setEnabled(state)

    def _lock_buttons(self, buttons: Optional[BUTTON_GROUPS] = None) -> None:
        """Lock buttons.

        buttons : Optional[BUTTON_GROUPS]
            Button group enum. If None, all buttons will be locked.
        """
        buttons = buttons.value if buttons is not None else self.buttons.keys()
        button_states = dict(zip(buttons, [False] * len(buttons)))
        self._change_button_states(button_states)

    def _unlock_buttons(self, buttons: Optional[BUTTON_GROUPS] = None) -> None:
        """Unlock buttons.

        buttons : Optional[BUTTON_GROUPS]
            Button group enum. If None, all buttons will be unlocked.
        """
        buttons = buttons.value if buttons is not None else self.buttons.keys()
        button_states = dict(zip(buttons, [True] * len(buttons)))
        self._change_button_states(button_states)

    def _get_settings_dict(self) -> Dict[str, Any]:
        """Create a dictionary of all specified settings that are needed for
        fetching jobs. Includes settings from the form settings layout and work
        location checkboxes.

        Returns
        -------
        settings_dict : Dict[str, Any]
            Job settings dictionary.
        """
        settings_dict = self.form_settings_layout.get_settings_dict()
        work_loc_list = self.work_location_layout.get_work_location_list()
        settings_dict[C.URL_PARAM_WORK_LOCATION] = work_loc_list
        return settings_dict

    def _check_settings_dict(self, settings_dict: Dict[str, Any]) -> bool:
        """Check the settings dictionary for empty settings ('', None, []).
        Shows a warning message box if one of the settings was not specified.

        Parameters
        ----------
        settings_dict : Dict[str, Any]
            Settings dictionary.

        Returns
        -------
        bool
            True if all settings were specified, False otherwise.
        """
        for param, value in settings_dict.items():
            if value in ("", None, []):
                QMessageBox.warning(
                    self, "Settings error", "Please enter all settings"
                )
                return False
        return True

    def _check_continue_results_saved(self, action) -> bool:
        """Check if the current results have been saved and ask the user to
        continue (through a messagebox) if they were not saved.

        Parameters
        ----------
        action : str
            Action which will be performed, can be one of `continue|quit`.

        Returns
        -------
        bool
            True if the user wants to continue and/or if the results already
            have been saved, False otherwise.
        """
        assert action in ("continue", "quit")

        if self._results_saved in (True, None):
            return True

        res = QMessageBox.question(
            self,
            "Saving results",
            "The current results have not been saved yet. Are you sure you "
            f"want to {action}?",
        )
        return res == QMessageBox.Yes

    def closeEvent(self, a0) -> None:
        """Override QWidget.closeEvent() to ask the user if they want to quit
        without saving.
        """
        if not self._check_continue_results_saved("quit"):
            a0.ignore()

    def _create_button(
        self,
        name: str,
        label: str,
        callback: Callable,
        enabled_by_default: bool = False
    ) -> None:
        """Create button with label and specify if enabled by default.
        Sets size policy of the button to minimum expanding horizontally,
        and fixed vertically.

        Parameters
        ----------
        name : str
            Button name.
        label : str
            Button label.
        callback : Callable
            Callback to connect to the button.
        enabled_by_default : bool
            Indicates if the button is enabled by default.

        """
        button = QPushButton(label)
        button.setEnabled(enabled_by_default)
        button.setSizePolicy(SIZE_MIN_EXPANDING, SIZE_FIXED)
        button.clicked.connect(callback)
        self.buttons[name] = button


class Worker(QThread):
    """Worker object to execute a method in a separate thread."""

    started = pyqtSignal()
    finished = pyqtSignal()
    result = pyqtSignal(object)

    def __init__(self, function, *func_args, **func_kwargs):
        """

        Parameters
        ----------
        function : func_type
            Callback to execute in run().
        func_args : Tuple
            Arguments to pass to the callback in `function`.
        func_kwargs : Dict[str, Any]
            Keyword arguments to pass to the callback in `function`.
        """
        super().__init__()

        self.function = function
        self.func_args = func_args
        self.func_kwargs = func_kwargs

        self.finished.connect(self.deleteLater)

    def run(self) -> None:
        """Run thread.

        Emits signals when the thread is started and finished, and for the
        result.
        """
        self.started.emit()
        res = self.function(*self.func_args, **self.func_kwargs)
        self.result.emit(res)
        self.finished.emit()


class PandasModel(QAbstractTableModel):
    """Custom QAbstractTableModel for DataFrames.
    Modified from:
    https://learndataanalysis.org/display-pandas-dataframe-with-pyqt5-qtableview-widget/
    """

    DATAFRAME_KEY_TO_COLUMN_NAME = {
        C.KEY_TITLE: "Title",
        C.KEY_COMPANY: "Company",
        C.KEY_LOCATION: "Location",
        C.KEY_DATE: "Date",
        C.KEY_HAS_JOB_DESCRIPTION: "Description",
    }

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self._data: DataFrame = data
        self._l = logger.getChild(self.__class__.__name__)

        self._icons = {
            True: QIcon(f"{PATH_ICONS}/tick.png"),
            False: QIcon(f"{PATH_ICONS}/cross.png"),
        }

    @property
    def df(self):
        return self._data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1]

    def data(self, index, role):
        if not index.isValid():
            return None

        value = self._data.iloc[index.row(), index.column()]
        if role == Qt.DisplayRole:
            # value can be a numpy.bool_, which makes `isinstance(value, bool)`
            # not usable
            if value not in (True, False):
                return str(value)
        elif role == Qt.DecorationRole:
            return self._icons.get(value, None)

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            key = self._data.columns[section]
            return self.DATAFRAME_KEY_TO_COLUMN_NAME.get(key, C.UNKNOWN)
        else:
            return super().headerData(section, orientation, role)

    def removeRows(self, row, count, parent=QModelIndex()):
        self._l.debug(f"Deleting rows from '{row}' to '{row + count - 1}'.")
        self.beginRemoveRows(parent, row, row + count - 1)
        for _ in range(count):
            self._data.drop(self._data.index[row], inplace=True)
        self.endRemoveRows()
        self.layoutChanged.emit()
        self._l.debug(f"Dataframe length after deleting: {self._data.shape[0]}")
        return True

    def sort(self, column, order):
        self._data.sort_values(
            self._data.columns[column],
            axis="rows",
            ascending=order == Qt.AscendingOrder,
            inplace=True,
        )
        self.layoutChanged.emit()


class JobTableViewer(QTableView):
    """Table view widget to display the jobs DataFrame."""

    DF_COLUMNS_TO_SHOW = [
        C.KEY_TITLE,
        C.KEY_COMPANY,
        C.KEY_LOCATION,
        C.KEY_DATE,
        C.KEY_HAS_JOB_DESCRIPTION,
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._l = logger.getChild(self.__class__.__name__)

        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the user interface of the widget."""
        self.setShowGrid(False)
        self.setSizeAdjustPolicy(QHeaderView.AdjustToContents)
        self.setSizePolicy(SIZE_MIN_EXPANDING, SIZE_MIN_EXPANDING)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        # NOTE: ContiguousSelection is needed as PandasModel.removeRows() does
        # not support arbitrary row selection
        self.setSelectionMode(QAbstractItemView.ContiguousSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSortingEnabled(True)

        h_header = self.horizontalHeader()
        v_header = self.verticalHeader()
        h_header.setSectionResizeMode(QHeaderView.ResizeToContents)
        h_header.setSortIndicatorShown(True)
        v_header.setSectionResizeMode(QHeaderView.ResizeToContents)

    def display_jobs(self, df: DataFrame) -> None:
        """Display all jobs from the dataframe. Only shows the column specified
        in DF_COLUMNS_TO_SHOW.

        Parameters
        ----------
        df : DataFrame
        """
        model = PandasModel(df.loc[:, self.DF_COLUMNS_TO_SHOW])
        self.setModel(model)

    def get_current_dataframe(self) -> DataFrame:
        """Return the current dataframe that is displayed.

        Returns
        -------
        DataFrame
        """
        return self.model().df

    def get_current_dataframe_indices(self) -> pd.Index:
        """Return the current dataframe indices that are displayed.

        Returns
        -------
        pandas.Index
        """
        return self.get_current_dataframe().index

    def keyPressEvent(self, e: Optional[QKeyEvent]) -> None:
        """Override QTableView.keyPressEvent to add functionality for
        deleting selected rows with the Delete key.
        """
        if e.key() == Qt.Key_Delete:
            self._l.debug("Delete key pressed")
            rows = self.selectionModel().selectedRows()
            if len(rows) == 0:
                return
            self.model().removeRows(rows[0].row(), len(rows), rows[0])
            self.selectionModel().clearSelection()
        super().keyPressEvent(e)


class FormSettingsLayout(QFormLayout):
    """Layout for specifying form settings.

    It generates input fields with corresponding labels for the setting names
    passed to its constructor, and organizes these settings in a form layout
    with setting names on the left and the input fields on the right.

    """

    def __init__(
        self,
        setting_params: Iterable[str],
        default_values: Optional[Dict[str, str]] = None,
        *args,
        **kwargs,
    ):
        """
        Parameters
        ----------
        setting_params : Iterable[str]
            An iterable of setting names.
        default_values : Optional[Dict[str, str]]
            Dictionary of default values for settings, with setting names as
            keys and setting values as values.
        """
        assert set(default_values).issubset(setting_params)

        super().__init__(*args, **kwargs)

        self._l = logger.getChild(self.__class__.__name__)
        self._default_values = default_values
        # Dictionary to convert the label names to parameter names
        self._labels_to_params = {}

        for param in setting_params:
            default_value = default_values.get(param, None)
            if isinstance(default_value, int):
                input_field = QSpinBox()
                input_field.setValue(default_value)
            else:
                input_field = QLineEdit()
                if default_value is not None:
                    input_field.setText(str(default_value))

            input_field.setSizePolicy(SIZE_MIN_EXPANDING, SIZE_FIXED)

            label = param.replace("_", " ").capitalize()
            self._labels_to_params[label] = param
            self.addRow(label, input_field)

    def get_settings_dict(self) -> Dict[str, str]:
        """Convert the settings in the input fields to a dictionary.

        Returns
        -------
        res : Dict[str, str]
        """
        self._l.debug("Creating a settings dictionary")
        res = {}
        for row_id in range(self.rowCount()):
            label = self.itemAt(row_id, LABEL_ROLE).widget().text()
            field = self.itemAt(row_id, FIELD_ROLE).widget()

            if isinstance(field, QLineEdit):
                field = field.text()
            elif isinstance(field, QSpinBox):
                field = field.value()
            else:
                raise NotImplementedError

            param = self._labels_to_params[label]
            res[param] = field

        return res


class WorkLocationLayout(QVBoxLayout):
    """Layout with three checkboxes to specify the work location."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.labels = {}
        self.checkboxes = {}

        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the user interface of the widget."""
        layout_checkbox = QVBoxLayout()
        for i, wl in enumerate(WL):
            self.checkboxes[wl] = QCheckBox(
                wl.name.replace("_", " ").capitalize()
            )
            layout_checkbox.addWidget(self.checkboxes[wl])

        layout_b = QHBoxLayout()
        layout_b.addStretch(1)
        layout_b.addLayout(layout_checkbox)
        layout_b.addStretch(10)

        self.addWidget(QLabel("Work locations:"))
        self.addLayout(layout_b)

    def get_work_location_list(self) -> List[WL]:
        """Get a list of checked work locations.

        Returns
        -------
        wl_list : List[WL]
            List of work locations.
        """
        wl_list = [wl for wl, cb in self.checkboxes.items() if cb.isChecked()]
        return wl_list


class FilterKeywordsLayout(QVBoxLayout):
    """Layout with label and text edit box for specifying filter keywords.
    """

    def __init__(
        self,
        name: str,
        default_keywords: Optional[List[str]] = None,
        *args,
        **kwargs,
    ):
        """
        Parameters
        ----------
        name : str
            Layout name, will be put above the text edit box as a label.
        default_keywords : Optional[List[str]]
            List of default filter keywords that will be set in the
            text box.
        """
        super().__init__(*args, **kwargs)

        self.name = name
        self.default_keywords = default_keywords

        self._init_ui()
        if self.default_keywords is not None:
            self.set_keywords(self.default_keywords)

    def _init_ui(self) -> None:
        """Initialize the user interface of the widget."""
        self.text_edit = QPlainTextEdit()
        self.text_edit.setSizePolicy(SIZE_MIN_EXPANDING, SIZE_FIXED)
        self.text_edit.setFixedHeight(60)
        self.text_edit.setToolTip(
            "Specify filter keywords, must be separated by a `,`"
        )

        self.addWidget(QLabel(f"{self.name}:"))
        self.addWidget(self.text_edit)

    def set_keywords(
        self, filter_keywords: Iterable[str]
    ) -> None:
        """Set the contents of the iterable to the text box.

        Joins the contents of the iterable with ', ' to create one string.

        Parameters
        ----------
        filter_keywords : Iterable[str]
            Iterable of filter keywords.

        """
        title_str = ", ".join(filter_keywords)
        self.text_edit.setPlainText(title_str)

    def get_keyword_list(self) -> Optional[List[str]]:
        """Create and return a list of filter keywords.

        Splits the user input from the text box on the ',' and adds the
        resulting keywords to a list.

        Returns
        -------
        Optional[List[str]]
            Returns None if no keywords were specified.

        """
        text = self.text_edit.toPlainText()
        if text == "":
            return None
        filter_list = text.split(",")
        return [w.strip() for w in filter_list if w != ""]


class QProgressDialogWithConfirmation(QProgressDialog):
    """
    References
    ----------
    [1] https://stackoverflow.com/questions/71226523/how-to-intercept-qprogressdialog-cancel-click
    [2] https://forum.qt.io/topic/78604/how-to-disable-esc-key-close-the-qprogressdialog/11
    [3] https://doc.qt.io/qt-5/qevent.html#accepted-prop
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Override Cancel-button functionality
        button = self.findChild(QPushButton)
        button.clicked.disconnect()
        button.clicked.connect(self.cancel)

    def cancel(self):
        """Override cancel to prompt the user with a confirmation about
        cancelling the action.
        """
        res = QMessageBox.question(
            self,
            "Stop action",
            "Are you sure you want to stop the current action?"
        )
        if res != QMessageBox.Yes:
            return

        self.canceled.emit()
        return super().cancel()

    def event(self, a0):
        """Override event to catch an escape-key press and remove its
        functionality (closing the window). See [2].
        """
        if isinstance(a0, QKeyEvent) and a0.key() == Qt.Key_Escape:
            # The event should be accepted here to prevent it from being
            # propagated to the parent class [3].
            a0.accept()
            return True

        return super().event(a0)

    # def reject(self):
    #     # TODO: according to [1], overriding reject should prevent the Esc
    #     #  button from closing the window. Unfortunately, this is not the case.
    #     pass

    def closeEvent(self, a0):
        """Override closeEvent to prompt a confirmation to the user when the 'X'
        is clicked. See [1].
        """
        if a0.spontaneous():
            a0.ignore()
            self.cancel()
            return

        return super().closeEvent(a0)


def question_messagebox(parent: QWidget, title: str, text: str) -> QMessageBox:
    """Create question QMessageBox.

    Parameters
    ----------
    parent : QWidget
        Parent widget.
    title : str
        Window title.
    text : str
        Text on the dialog window.

    Returns
    -------
    mb : QMessageBox
    """
    mb = QMessageBox(parent)
    mb.setIcon(QMessageBox.Question)
    mb.setText(text)
    mb.setWindowTitle(title)
    mb.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

    return mb


def main() -> None:
    session = LinkedinSession()
    scraper = LinkedinJobScraper(session)

    """Main app initialization and main loop."""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    cwd = os.path.dirname(__file__)
    widget = MainWindow(scraper, f"{cwd}/../results")
    widget.show()
    app.exec_()

    logger.handlers.clear()
    session.close()
    sys.exit()


if __name__ == "__main__":
    main()
