# -*- coding: utf-8 -*-
"""
Created on Thu Feb 29 14:44:11 2024

@author: Hans
"""
import os
import re
from datetime import datetime
from enum import Enum
from random import uniform
from time import sleep
from typing import Any, Dict, Iterable, Optional, Tuple

import pandas
from bs4 import BeautifulSoup
from pandas import DataFrame
from requests import Session
from requests.exceptions import ConnectionError as ConnectionErrorReq
from requests.exceptions import HTTPError, Timeout

import constants as C
from logger import logger

# fmt: off
TITLE_KEYWORDS_TO_ALWAYS_KEEP = ("python",)
TITLE_KEYWORDS_TO_KEEP = (
    "developer", "ontwikkelaar", "software", "programmer", "back end",
    "back-end", "backend", "full-stack", "fullstack", "full stack", "robotic",
)

TITLE_KEYWORDS_TO_DISCARD = (
    "java", "php", "c++", "c#", "dotnet", ".net", "plc", "mendix", "oracle",
    "data", "front end", "front-end", "frontend", "golang", "scala", "ruby",
    "powerbi", "rust", "react", "internship", "principal", "typescript",
    "werktuig", "gis", "angular", "stage", "usd/year"
)
# fmt: on


class BadStatusCode(Exception):
    """Exception for an unexpected HTTP status code."""

    def __init__(self, res):
        self._res = res
        super().__init__()

    def __str__(self):
        return f"Bad status code: {self._res}"


class WL(Enum):
    """LinkedIn work locations."""

    ON_SITE = "1"
    REMOTE = "2"
    HYBRID = "3"


class LinkedinSession:
    HEADERS = {
        "User-Agent": "I just want linkedin to fix their search engine",
        "Connection": "keep-alive",
    }

    MAX_TRIES = 20
    MAX_TIMEOUT_ON_429 = 5  # maximum timeout in sec for a 429 status code
    MIN_TIMEOUT_ON_429 = 1  # minimum timeout in sec for a 429 status code

    def __init__(self, test_session=False):
        self.session = None

        self._l = logger.getChild(self.__class__.__name__)

        self.start_session()
        if test_session:
            self.test_session()

    def start_session(self) -> None:
        """Start a new requests.Session. An already existing session will be
        closed first.
        """
        self._l.info("Starting session")
        if self.session is not None:
            self.close()

        self.session = Session()

    def test_session(self) -> None:
        """Convenience method to test the session by retrieving a job page.
        get_html() will raise any errors depending on the received HTTP
        status codes.
        """
        self._l.info("Testing session")
        self.get_html(C.URL_TEST_CONNECTION)

    # TODO-3: maybe use/create a task decorator that can execute this method
    #  several times depending (with exponential backoff) on the raised
    #  exceptions
    def get_html(
        self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs
    ) -> BeautifulSoup:
        """Get the HTML contents of page.

        Parameters
        ----------
        url : str
        headers : Optional[Dict[str, str]]
            Dictionary with headers to pass during getting the page contents.

        Returns
        -------
        res : BeautifulSoup
            HTML contents.

        Raises
        ------
        SystemError
            If requests.get() raises an error.
        TimeoutError
            If the HTTP status code is 429.
        BadStatusCode
            If the HTTP status code is anything other than 200 or 429.

        """
        self._l.conn(f"Fetching HTML content from url: {url}")
        if headers is None:
            headers = self.HEADERS

        res = None
        for i in range(self.MAX_TRIES):
            self._l.conn(f"Tries remaining: {self.MAX_TRIES - i}")

            try:
                res = self.session.get(url, headers=headers, **kwargs)
            except (ConnectionErrorReq, HTTPError, Timeout, SystemError) as e:
                self._l.conn(f"Requests error: {repr(e)}. Will try again.")
                continue

            if (sc := res.status_code) == 200:
                self._l.conn(f"Received valid response from url: {url}.")
                break
            elif sc == 429:
                self._l.conn(f"Too many requests (status code 429).")
                sleep(uniform(self.MIN_TIMEOUT_ON_429, self.MAX_TIMEOUT_ON_429))
            elif sc == 400:
                self._l.conn("Bad request (status code 400)")
                break
            else:
                self._l.conn(f"Unexpected status code: {sc}. Will try again")

        if res is None:
            self._l.error("Error when using requests.get().")
            raise SystemError(
                "Error when using requests.get(). Check internet connection "
                "and restart the session"
            )

        if sc == 429:
            self._l.error(f"Too many requests for url: {url}")
            raise TimeoutError()
        elif sc != 200:
            self._l.error(f"Bad status code for url: {url}")
            raise BadStatusCode(sc)

        return BeautifulSoup(res.content, features="lxml")

    def close(self) -> None:
        """Close the session."""
        self.session.close()


class LinkedinJobScraper:

    LOCATION = "Nederland"
    N_DAYS = 1
    GEO_ID = "102890719"
    WORK_LOCATION = (WL.HYBRID, WL.REMOTE, WL.ON_SITE)

    def __init__(self, session):
        self.session: LinkedinSession = session

        self._l = logger.getChild(self.__class__.__name__)

        self._n_jobs_per_page = None

    @property
    def n_jobs_per_page(self) -> int:
        """Number of jobs per job page.

        Will determine this on the first call, because it is session
        dependent.
        """
        if self._n_jobs_per_page is None:
            self._l.debug("Determining the number of jobs per page")
            html = self._get_job_page(C.URL_TEST_CONNECTION)
            # TODO-2: is there a better way of determining this?
            if str(html).startswith("<!DOCTYPE html>"):
                self._n_jobs_per_page = 10
            else:
                self._n_jobs_per_page = 25
            self._l.debug(f"Number of jobs per page: {self._n_jobs_per_page}")

        return self._n_jobs_per_page

    def scrape_jobs(
        self,
        keywords: str,
        n_days: int = N_DAYS,
        location: str = LOCATION,
        geo_id: str = GEO_ID,
        work_location: Tuple[WL] = WORK_LOCATION,
        page_start: int = 0,
    ) -> Tuple[DataFrame, Dict[str, Any]]:
        """Get all jobs for the passed parameters.

        Parameters
        ----------
        keywords : str
            Keywords to search for.
        n_days : int
            The past number of days to search in.
        location : str
            Area to search in.
        geo_id : str
            Geo identification.
        work_location : Tuple[WL]
            Tuple of work locations (on site, remote, hybrid).
        page_start : str
            Page number to start searching from.

        Returns
        -------
        df : DataFrame
            Dataframe where each row represents a jobs.
        metadata : Dict[str, Any]
            Information about the search query.
        """
        self._l.info(
            f"Fetching '{keywords}' jobs from past {n_days} day(s) with "
            f"location '{location}', geo ID '{geo_id}', and work location: "
            f"{work_location}."
        )

        metadata = {
            C.URL_PARAM_N_SECONDS: convert_days_to_sec(n_days),
            C.URL_PARAM_WORK_LOCATION: self._join_wl(work_location),
            C.URL_PARAM_KEYWORDS: keywords,
            C.URL_PARAM_LOCATION: location,
            C.URL_PARAM_GEO_ID: geo_id,
        }
        page = page_start
        job_list = []
        while True:
            self._l.info(f"Fetching jobs from page {page}")
            url = C.URL_JOB_PAGE.format(
                start=page * self.n_jobs_per_page, **metadata
            )
            html = self._get_job_page(url)
            if html is None:
                break

            jobs = html.find_all("li")
            if len(jobs) == 0:
                break

            for job in jobs:
                job_dict = self._extract_info_from_single_job_on_job_page(job)
                job_list.append(job_dict)

            page += 1

        df = DataFrame(job_list)
        df[C.KEY_HAS_JOB_DESCRIPTION] = False

        return df, metadata

    def _get_job_page(self, url: str) -> Optional[BeautifulSoup]:
        """Get job page with error handling.

        Parameters
        ----------
        url : str

        Returns
        -------
        html : Optional[BeautifulSoup]
            Contents of the page. Returns None when an error was raised
            during fetching of the page.
        """
        try:
            html = self.session.get_html(url)
        except (TimeoutError, BadStatusCode, SystemError) as e:
            self._l.warning(
                f"Error when fetching job page: {repr(e)}. It is possible "
                f"that not all available job pages have been scraped."
            )
            html = None

        return html

    def _extract_info_from_single_job_on_job_page(
        self, html_job: BeautifulSoup
    ) -> Dict[str, str]:
        """Extract job information from a single job list entry off of a job
        page.

        Parameters
        ----------
        html_job : BeautifulSoup
            Job list entry from a job page.

        Returns
        -------
        Dict[str, str]
            Dictionary with details (title, company, location, link, id) about
            the job. Parameters which are not found will be marked as UNKNOWN.

        """
        title = html_job.find("h3", {"class": "base-search-card__title"})
        company = html_job.find("h4", {"class": "base-search-card__subtitle"})
        job_location = html_job.find(
            "span", {"class": "job-search-card__location"}
        )
        link = html_job.find(href=re.compile("linkedin.com/jobs/view"))
        date = html_job.find(
            "time", {"class": "job-search-card__listdate--new"}
        )

        title = self._get_html_text_and_strip(title)
        company = self._get_html_text_and_strip(company)
        job_location = self._get_html_text_and_strip(job_location)
        job_location = (
            job_location.split(",")[0]
            if job_location is not None
            else C.UNKNOWN
        )
        link = link.get("href").split("?")[0] if link is not None else C.UNKNOWN
        job_id = link.split("-")[-1] if link is not None else C.UNKNOWN
        date = date.get("datetime") if date is not None else C.UNKNOWN

        return {
            C.KEY_TITLE: title if title is not None else C.UNKNOWN,
            C.KEY_COMPANY: company if company is not None else C.UNKNOWN,
            C.KEY_LINK: link,
            C.KEY_JOB_ID: job_id,
            C.KEY_LOCATION: job_location,
            C.KEY_DATE: date,
        }

    def determine_n_jobs(
        self,
        keywords: str,
        n_days: int = N_DAYS,
        location: str = LOCATION,
        geo_id: str = GEO_ID,
        work_location: Tuple[WL] = WORK_LOCATION,
    ) -> Optional[int]:
        """Determine the total number of jobs for the given parameters.

        Parameters
        ----------
        keywords : str
            Keywords to search for.
        n_days : int
            The past number of days to search in.
        location : str
            Area to search in.
        geo_id : str
            Geo identification.
        work_location : Tuple[WL]
            Tuple of work locations (on site, remote, hybrid).

        Returns
        -------
        Optional[int]
            Number of jobs. None if the HTML class was not found.

        """
        self._l.info(
            f"Determining number of jobs for '{keywords}' from past {n_days} "
            f"day(s) with location '{location}' and geo ID '{geo_id}', and "
            f"work location: {work_location}."
        )
        url = C.URL_FOR_N_JOBS.format(
            keywords=keywords,
            n_seconds=convert_days_to_sec(n_days),
            location=location,
            geo_id=geo_id,
            work_location=self._join_wl(work_location),
        )
        html = self.session.get_html(url)

        html_n_jobs = html.find("span", "results-context-header__job-count")
        if html_n_jobs is None:
            return None
        else:
            return int(html_n_jobs.text.strip("+ ").replace(",", ""))

    def get_html_job_description(self, job_id: str) -> Optional[BeautifulSoup]:
        """Get the description in HTML for a single job.

        Parameters
        ----------
        job_id : str
            Job identifier.

        Returns
        -------
        descr : Optional[BeautifulSoup]
            Job description. None if the HTML class was not found.

        """
        self._l.info(f"Fetching job description for job with ID: {job_id}")
        url = C.URL_SINGLE_JOB.format(job_id=job_id)
        try:
            html = self.session.get_html(url)
        except (TimeoutError, BadStatusCode):
            return None

        descr = html.find("div", {"class": "show-more-less-html__markup"})
        return descr

    # TODO-1
    def get_job_descriptions(
        self, df: DataFrame, index_filter: Optional[pandas.Index] = None
    ) -> DataFrame:
        """Get descriptions for jobs in the dataframe.

        Optionally can pass an index filter to select jobs of which to fetch the
        descriptions.

        Adds two columns to the dataframe:
            - description_html: job description in HTML format
            - has_job_description: boolean to indicate if a description is
            present

        Parameters
        ----------
        df : DataFrame
            Dataframe with jobs.
        index_filter : Optional[pandas.Index]
            Series of indices for which to fetch the descriptions. If None,
            the descriptions for all entries will be fetched.

        Returns
        -------
        DataFrame
            Dataframe containing only the jobs for which the description was
            fetched.

        """

        df_temp = df.loc[index_filter, :] if index_filter is not None else df
        if C.KEY_JOB_DESCRIPTION not in df:
            df[C.KEY_JOB_DESCRIPTION] = None
        for row_id, row in df_temp.iterrows():
            descr = self.get_html_job_description(row[C.KEY_JOB_ID])
            df.loc[row_id, C.KEY_JOB_DESCRIPTION] = (
                descr.prettify() if descr is not None else C.UNKNOWN
            )

        df[C.KEY_HAS_JOB_DESCRIPTION] = ~df[C.KEY_JOB_DESCRIPTION].isnull()

        return df.loc[df[C.KEY_HAS_JOB_DESCRIPTION], :]

    @staticmethod
    def _join_wl(work_location: Iterable[WL]) -> str:
        """Combine an iterable of WL entries to one string of WL values
        separated by a comma.

        Parameters
        ----------
        work_location : Iterable[WL]
            Iterable of WL entries.

        Returns
        -------
        str
            String of combined WL entries.

        Examples
        --------
        >>> wl_str = LinkedinJobScraper._join_wl((WL.HYBRID, WL.REMOTE))
        >>> print(wl_str)
        3,2

        """
        wl_list = [wl.value for wl in work_location]
        return ",".join(wl_list)

    @staticmethod
    def _get_html_text_and_strip(
        html: Optional[BeautifulSoup],
    ) -> Optional[str]:
        """Get the text from an HTML object and strip it.

        Parameters
        ----------
        html : Optional[BeautifulSoup]
            HTML object.

        Returns
        -------
        Optional[str]
            Stripped text of the HTML object. None if `html` was None.

        """
        return html.text.strip() if html is not None else html


# TODO-1
def filter_job_titles(
    df: DataFrame,
    keywords_always_keep: Optional[Iterable[str]] = None,
    keywords_keep: Optional[Iterable[str]] = None,
    keywords_discard: Optional[Iterable[str]] = None,
    index_filter: Optional[pandas.Index] = None,
) -> DataFrame:
    """Filter jobs based on the presence of keywords in the titles.

    A job will be kept if its title adheres to the following logic:
        contains_keywords_to_always_keep OR (contains_keywords_to_keep AND NOT
        contains_keywords_to_discard)

    Optionally can pass an index filter to select jobs of which to check the
    titles.

    Parameters
    ----------
    df : DataFrame
        Dataframe with jobs.
    keywords_always_keep : Optional[Iterable[str]]
        Iterable of keywords to always keep.
    keywords_keep : Optional[Iterable[str]]
        Iterable of keywords to keep if the title does not also contain
        keywords to drop.
    keywords_discard : Optional[Iterable[str]]
        Iterable of keywords to drop.
    index_filter : Optional[pandas.Index]
        Indices for which to filter on job titles. If None, all job titles will
        be checked.

    Returns
    -------
    DataFrame
        Dataframe containing only the jobs for which titles passed the check.

    Raises
    ------
    AssertionError
        If all keyword iterables are None.

    """
    assert not (
        keywords_always_keep is None
        and keywords_keep is None
        and keywords_discard is None
    )

    if index_filter is not None:
        raise NotImplementedError(
            "The use of `index_filter` is currently not implemented."
        )
    # df_temp = df.loc[index_filter, :] if index_filter is not None else df

    for type_, keywords in zip(
        ("always_keep", "keep", "discard"),
        (keywords_always_keep, keywords_keep, keywords_discard),
    ):
        if keywords is None:
            continue
        df[C.KEY_TITLE_CONTAINS_KEYWORDS.format(type_)] = df[C.KEY_TITLE].apply(
            contains_keywords, args=(keywords,)
        )

    if keywords_always_keep is not None:
        i_always_keep = df[C.KEY_TITLE_CONTAINS_KEYWORDS.format("always_keep")]
    else:
        i_always_keep = False

    if keywords_keep is not None:
        i_keep = df[C.KEY_TITLE_CONTAINS_KEYWORDS.format("keep")]
    else:
        i_keep = True

    if keywords_discard is not None:
        i_discard = df[C.KEY_TITLE_CONTAINS_KEYWORDS.format("discard")]
    else:
        i_discard = True

    df[C.KEY_KEEP_JOB_AFTER_TITLE_FILTER] = i_always_keep | (
        i_keep & ~i_discard
    )

    return df[df[C.KEY_KEEP_JOB_AFTER_TITLE_FILTER]]


# TODO-1
def filter_job_descriptions(
    df: DataFrame, keyword: str, index_filter: Optional[pandas.Index] = None
) -> DataFrame:
    """Filter job descriptions based on a keyword.

    Checks if the description contains the keyword and sets a new column
    in the dataframe accordingly.

    Optionally can pass an index filter to select jobs of which to check the
    titles.

    Parameters
    ----------
    df : DataFrame
        Dataframe with jobs.
    keyword : str
        Keyword to search for in the job description.
    index_filter : Optional[pandas.Index]
        Series of indices for which to filter on the descriptions. If None, the
        descriptions for all jobs will be checked.

    Returns
    -------
    DataFrame
        Dataframe containing only jobs of which the description contains the
        `keyword`, or jobs for which the description was failed to be retrieved.

    Raises
    ------
    AssertionError
        If the dataframe does not contain the column for job description.
    """
    assert C.KEY_JOB_DESCRIPTION in df

    df_temp = df.loc[index_filter, :] if index_filter is not None else df

    df[C.KEY_DESCR_CONTAINS_KEYWORD] = None
    for row_id, row in df_temp.iterrows():
        if row[C.KEY_JOB_DESCRIPTION] is None:
            continue
        elif row[C.KEY_JOB_DESCRIPTION] is not C.UNKNOWN:
            contains_keyword = keyword in row[C.KEY_JOB_DESCRIPTION].lower()
        else:
            contains_keyword = C.UNKNOWN

        df.loc[row_id, C.KEY_DESCR_CONTAINS_KEYWORD] = contains_keyword

    return df[df[C.KEY_DESCR_CONTAINS_KEYWORD].isin([True, C.UNKNOWN])]


def convert_days_to_sec(n_days: int) -> int:
    """Convert number of days to number of seconds passed.

    Parameters
    ----------
    n_days : int
        Number of days

    Returns
    -------
    int
        Number of seconds corresponding to `n_days`.

    """
    return n_days * 3600 * 24


def contains_keywords(title: str, keywords: Iterable[str]) -> bool:
    """Checks if the title contains any of the passed keywords.

    Parameters
    ----------
    title : str
    keywords : Iterable[str]
        Iterable of keywords to search for.

    Returns
    -------
    bool
        True if any of the keywords are in `title`, False if not.

    """
    title = title.lower()
    for keyword in keywords:
        if keyword.lower() in title:
            return True
    return False


def save_job_dataframe_to_html_file(
    df: DataFrame,
    metadata: Dict[str, Any],
    filename: Optional[str] = None,
    folder: str = "results",
) -> None:
    """Save job dataframe to an HTML file.

    Parameters
    ----------
    df : DataFrame
        Dataframe with jobs.
    metadata : Dict[str, Any]
        Information about the search query which was used to get the jobs.
    filename : Optional[str]
        Name of the file to save in. If None, a filename will be generated
        according to the template:
        '[date]_[search_keyword]_wl=[work_location].html'
    folder : str
        Folder to save the results in. Will be created if it doesn't exist.

    Raises
    ------
    AssertionError
        If the passed filename does not end with '.html'.

    """
    if filename is None:
        keywords = metadata.get(C.URL_PARAM_KEYWORDS, C.UNKNOWN)
        work_location = metadata.get(C.URL_PARAM_WORK_LOCATION, C.UNKNOWN)
        date = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{date}_{keywords}_wl={work_location}.html"
    else:
        assert filename.endswith(".html")

    if not os.path.isdir(folder):
        os.mkdir(folder)

    with open(f"{folder}/{filename}", "w", encoding="utf-8") as f:
        f.write("<html><body>")
        for row_id, row in df.iterrows():
            f.write(
                C.HTML_JOB_TITLE.format(
                    link=row.get(C.KEY_LINK, C.UNKNOWN),
                    title=row.get(C.KEY_TITLE, C.UNKNOWN),
                    company=row.get(C.KEY_COMPANY, C.UNKNOWN),
                    location=row.get(C.KEY_LOCATION, C.UNKNOWN),
                )
            )
            f.write(str(row.get(C.KEY_JOB_DESCRIPTION, C.UNKNOWN)))
            f.write(C.HTML_JOB_SEPARATOR)
        f.write("</body></html>")
