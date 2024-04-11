# -*- coding: utf-8 -*-
"""
Created on Mon Mar 11 14:16:09 2024

@author: Hans
"""

import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Union

import pandas as pd
from pandas import DataFrame
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt5.QtGui import QIcon, QKeyEvent
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QSizePolicy, QSpinBox, QTableView, QVBoxLayout, QWidget)

import constants as C
from job_scraper import (
    TITLE_KEYWORDS_TO_ALWAYS_KEEP, TITLE_KEYWORDS_TO_DISCARD,
    TITLE_KEYWORDS_TO_KEEP, WL, BadStatusCode, LinkedinJobScraper,
    LinkedinSession, filter_job_descriptions, filter_job_titles,
    save_job_dataframe_to_html_file)
from logger import CONN, DEBUG, INFO, logger

logger.setLevel(CONN)

SIZE_FIXED = QSizePolicy.Fixed
SIZE_MIN_EXPANDING = QSizePolicy.MinimumExpanding

LABEL_ROLE = QFormLayout.LabelRole
FIELD_ROLE = QFormLayout.FieldRole

PATH_ICONS = f"{os.path.dirname(__file__)}\\icons"


class MainWindow(QWidget):
    MIN_WIDTH = 1280
    MIN_HEIGHT = 720

    def __init__(
        self,
        session: LinkedinSession,
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

        self.session = session
        self.scraper = scraper
        self.save_folder = save_folder

        self._l = logger.getChild(self.__class__.__name__)

        self.df = None
        self.metadata = None

        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        """Initialize all UI elements."""
        self.setWindowTitle("LinkedIn Job Scraper")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.setStyleSheet(
            "QPushButton {font: 10pt Times} " "QLabel {font: 10pt Times}"
        )
        self.setWindowIcon(QIcon(f"{PATH_ICONS}/linkedin-icon-filled-256.png"))

        # Left side widgets
        self.settings_groupbox = QGroupBox("Settings")
        self.settings_groupbox.setSizePolicy(SIZE_MIN_EXPANDING, SIZE_FIXED)

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
            "always_keep": TitleFiltersLayout(
                "Title keywords to always keep", TITLE_KEYWORDS_TO_ALWAYS_KEEP
            ),
            "keep": TitleFiltersLayout(
                "Title keywords to keep", TITLE_KEYWORDS_TO_KEEP
            ),
            "discard": TitleFiltersLayout(
                "Title keyword to discard", TITLE_KEYWORDS_TO_DISCARD
            ),
        }
        self.description_filter_input = QLineEdit()
        self.description_filter_input.setText("python")
        self.buttons = {
            "test_session": create_button("Test session", True),
            "get_n_jobs": create_button("Get number of jobs", True),
            "scrape_jobs": create_button("Fetch jobs", True),
            "filter_job_titles": create_button("Filter job titles"),
            "get_job_descriptions": create_button("Fetch job descriptions"),
            "filter_job_descriptions": create_button("Filter job descriptions"),
            "save_results": create_button("Save results"),
            "reset_table_view": create_button("Reset filters"),
        }

        # Right side widgets
        jobs_groupbox = QGroupBox("Jobs")
        self.job_table = JobTableViewer()

        # Add widgets to layout
        layout = QHBoxLayout(self)

        layout_descr_filter = QHBoxLayout()
        layout_descr_filter.addWidget(QLabel("Job description filter"))
        layout_descr_filter.addWidget(self.description_filter_input)

        layout_settings = QVBoxLayout(self.settings_groupbox)
        layout_settings.addLayout(self.form_settings_layout)
        layout_settings.addLayout(self.work_location_layout)
        for tfl in self.title_filter_layouts.values():
            layout_settings.addLayout(tfl)
        layout_settings.addLayout(layout_descr_filter)

        layout_l = QVBoxLayout()
        layout_l.addWidget(self.settings_groupbox)
        layout_l.addStretch()
        for button in self.buttons.values():
            layout_l.addWidget(button)

        jobs_groupbox_layout = QVBoxLayout(jobs_groupbox)
        jobs_groupbox_layout.addWidget(self.job_table)

        layout.addLayout(layout_l)
        layout.addWidget(jobs_groupbox, 1)

    def _connect_signals(self) -> None:
        """Connect the buttons to their corresponding callback methods."""
        self.buttons["test_session"].clicked.connect(
            self._callback_test_session
        )
        self.buttons["get_n_jobs"].clicked.connect(self._callback_get_n_jobs)
        self.buttons["scrape_jobs"].clicked.connect(self._callback_scrape_jobs)
        self.buttons["filter_job_titles"].clicked.connect(
            self._callback_filter_job_titles
        )
        self.buttons["get_job_descriptions"].clicked.connect(
            self._callback_get_job_descriptions
        )
        self.buttons["filter_job_descriptions"].clicked.connect(
            self._callback_filter_job_descriptions
        )
        self.buttons["save_results"].clicked.connect(
            self._callback_save_results
        )
        self.buttons["reset_table_view"].clicked.connect(
            self._callback_reset_table_view
        )

    def _callback_test_session(self) -> None:
        """Callback for the 'Test session' (test_session) button."""
        current_states = self._get_current_button_states()
        self._lock_buttons()
        try:
            self.session.test_session()
            current_states["get_n_jobs"] = True
            current_states["scrape_jobs"] = True
            QMessageBox.information(self, "Test session", "Testing successful.")
        except (SystemError, TimeoutError, BadStatusCode) as e:
            QMessageBox.critical(
                self, "Test session", f"Error during testing of session: {e}"
            )
        self._change_button_states(current_states)

    def _callback_get_n_jobs(self) -> None:
        """Callback for the 'Get number of jobs' (get_n_jobs) button.

        Gets the specified settings and checks them, and only continues if
        they are ok.
        """
        settings_dict = self._get_settings_dict()
        if not self._check_settings_dict(settings_dict):
            return

        current_states = self._get_current_button_states()
        self._lock_buttons()
        n_jobs = self.scraper.determine_n_jobs(**settings_dict)
        QMessageBox.information(
            self, "Number of jobs", f"Number of jobs: {n_jobs}"
        )
        self._change_button_states(current_states)

    def _callback_scrape_jobs(self) -> None:
        """Callback for the 'Fetch jobs' (scrape_jobs) button.

        Gets the specified settings and checks them, and only continues if
        they are ok. If the number of fetched jobs is zero, an information
        message box will be displayed
        """
        settings_dict = self._get_settings_dict()
        if not self._check_settings_dict(settings_dict):
            return

        self._lock_buttons()
        self.df, self.metadata = self.scraper.scrape_jobs(**settings_dict)
        if not self.df.empty:
            self.job_table.display_jobs(self.df)
            QMessageBox.information(
                self, "Fetch jobs", "Job fetching completed"
            )
            # TODO: bit ugly
            self._unlock_buttons()
            self._lock_buttons(["filter_job_descriptions"])
        else:
            QMessageBox.information(
                self, "Fetch jobs", "No jobs available with current settings"
            )
            self._unlock_buttons(["test_session", "get_n_jobs", "scrape_jobs"])

    def _callback_filter_job_titles(self) -> None:
        """Callback for the 'Filter job titles' (filter_job_titles) button.

        Checks if at least on of the filter text boxes contains keywords.
        Shows a warning message box if not.
        """
        filter_lists = [
            self.title_filter_layouts["always_keep"].get_title_filter_list(),
            self.title_filter_layouts["keep"].get_title_filter_list(),
            self.title_filter_layouts["discard"].get_title_filter_list(),
        ]
        if all(fl is None for fl in filter_lists):
            QMessageBox.warning(
                self, "Settings error", "Please enter some filters"
            )
            return

        current_button_states = self._get_current_button_states()
        self._lock_buttons()
        # TODO-4: only filter jobs that are currently displayed instead of
        #  all jobs?
        df_res = filter_job_titles(self.df, *filter_lists)
        self.job_table.display_jobs(df_res)
        self._change_button_states(current_button_states)

    def _callback_get_job_descriptions(self) -> None:
        """Callback for the 'Fetch job descriptions' (get_job_descriptions)
        button.

        Shows an information message box upon completion.
        """
        self._lock_buttons()
        current_indices = self.job_table.get_current_dataframe_indices()
        self._l.debug(f"Get job descriptions: {current_indices}")
        df_res = self.scraper.get_job_descriptions(self.df, current_indices)
        self.job_table.display_jobs(df_res)
        QMessageBox.information(
            self,
            "Fetch job descriptions",
            "Fetching of job descriptions is completed",
        )
        self._unlock_buttons()

    def _callback_filter_job_descriptions(self) -> None:
        """Callback for the 'Filter job descriptions' (filter_job_descriptions)
        button.

        Checks if a description filter was specified. Shows a warning message
        box if not.
        """
        keyword = self.description_filter_input.text()
        if keyword == "":
            QMessageBox.warning(
                self,
                "Filtering job descriptions",
                "Please enter a keyword to filter job descriptions",
            )
            return

        current_indices = self.job_table.get_current_dataframe_indices()
        df_res = filter_job_descriptions(self.df, keyword, current_indices)
        self.job_table.display_jobs(df_res)

    def _callback_save_results(self) -> None:
        """Callback for 'Save results' (save_results) button.

        Only saves the data of the jobs that are currently shown in the table
        view.
        """
        current_indices = self.job_table.get_current_dataframe_indices()
        save_job_dataframe_to_html_file(
            self.df.loc[current_indices, :],
            self.metadata,
            folder=self.save_folder,
        )
        QMessageBox.information(self, "Saving", "Saving is completed")

    def _callback_reset_table_view(self) -> None:
        """Callback for the 'Reset filters' (reset_table_view) button.

        Removes all applied filters and shows all the jobs that were fetched.
        """
        self.job_table.display_jobs(self.df)

    def _change_button_states(self, button_states: Dict[str, bool]) -> None:
        """Change button states.

        button_states : Dict[str, bool]
            Dictionary of button states with button names as keys and
            states as values.
        """
        for name, state in button_states.items():
            self.buttons[name].setEnabled(state)

    def _lock_buttons(self, buttons: Optional[Iterable[str]] = None) -> None:
        """Lock buttons.

        buttons : Optional[Iterable[str]]
            Iterable of button names to lock. If None,
            all buttons will be locked.
        """
        if buttons is None:
            buttons = self.buttons.keys()
        button_states = dict(zip(buttons, [False] * len(buttons)))
        self._change_button_states(button_states)

    def _unlock_buttons(self, buttons: Optional[Iterable[str]] = None) -> None:
        """Unlock buttons.

        buttons : Optional[Iterable[str]]
            Iterable of button names to unlock. If None,
            all buttons will be unlocked.
        """
        if buttons is None:
            buttons = self.buttons.keys()
        button_states = dict(zip(buttons, [True] * len(buttons)))
        self._change_button_states(button_states)

    def _get_current_button_states(self) -> Dict[str, bool]:
        """Return the current states (enabled or disabled) of all buttons.

        Returns
        -------
        Dict[str, bool]
            Dictionary with button names as keys and boolean as values (True for
            enabled, False for disabled).
        """
        return {
            name: button.isEnabled() for name, button in self.buttons.items()
        }

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
            False if one of the settings was not specified, True if ok.
        """
        for param, value in settings_dict.items():
            if value in ("", None, []):
                QMessageBox.warning(
                    self, "Settings error", "Please enter all settings"
                )
                return False
        return True


class PandasModel(QAbstractTableModel):
    """Custom QAbstractTableModel for DataFrames.
    Modified from:
    https://learndataanalysis.org/display-pandas-dataframe-with-pyqt5-qtableview-widget/
    """

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
            if value in (True, False):
                return self._icons[value]

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            col = self._data.columns[section].replace("_", " ").capitalize()
            return col
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
            ascending=True if order == Qt.AscendingOrder else False,
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


class TitleFiltersLayout(QVBoxLayout):
    """Layout with label and text edit box for specifying title filter
    keywords.
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
            List of default title filter keywords that will be set in the
            text box.
        """
        super().__init__(*args, **kwargs)

        self.name = name
        self.default_keywords = default_keywords

        self._init_ui()
        if self.default_keywords is not None:
            self.set_title_filter_keywords(self.default_keywords)

    def _init_ui(self) -> None:
        """Initialize the user interface of the widget."""
        self.text_edit = QPlainTextEdit()
        self.text_edit.setSizePolicy(SIZE_MIN_EXPANDING, SIZE_FIXED)
        self.text_edit.setFixedHeight(60)

        self.addWidget(QLabel(f"{self.name}:"))
        self.addWidget(self.text_edit)

    def set_title_filter_keywords(
        self, title_filter_keywords: Iterable[str]
    ) -> None:
        """Set the contents of the iterable to the text box.

        Joins the contents of the iterable with ', ' to create one string.

        Parameters
        ----------
        title_filter_keywords : Iterable[str]
            Iterable of title filter keywords.

        """
        title_str = ", ".join(title_filter_keywords)
        self.text_edit.setPlainText(title_str)

    def get_title_filter_list(self) -> Optional[List[str]]:
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


def create_button(label: str, enabled_by_default: bool = False) -> QPushButton:
    """Create button with label and specify if enabled by default.
    Sets size policy of the button to minimum expanding horizontally,
    and fixed vertically.

    Parameters
    ----------
    label : str
        Button label.
    enabled_by_default : bool
        Indicates if the button is enabled by default.

    Returns
    -------
    button : QPushButton
    """
    button = QPushButton(label)
    button.setEnabled(enabled_by_default)
    button.setSizePolicy(SIZE_MIN_EXPANDING, SIZE_FIXED)
    return button


def main() -> None:
    session = LinkedinSession()
    scraper = LinkedinJobScraper(session)

    """Main app initialization and main loop."""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    widget = MainWindow(session, scraper, "../results")
    widget.show()
    app.exec_()

    logger.handlers.clear()
    session.close()
    sys.exit()


if __name__ == "__main__":
    main()
