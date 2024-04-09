# Dataframe keys
KEY_DESCR_CONTAINS_KEYWORD = "descr_contains_keyword"
KEY_JOB_DESCRIPTION = "description_html"
KEY_TITLE_CONTAINS_KEYWORDS = "title_contains_{}_keyword"
KEY_KEEP_JOB_AFTER_TITLE_FILTER = "keep_job_after_title_filter"
KEY_TITLE = "title"
KEY_COMPANY = "company"
KEY_LINK = "link"
KEY_JOB_ID = "job_id"
KEY_LOCATION = "location"
KEY_HAS_JOB_DESCRIPTION = "has_job_description"
KEY_DATE = "date"

UNKNOWN = "UNKNOWN"

# URL stuff
URL_HOMEPAGE = "https://linkedin.com"
URL_JOB_SEARCH = (
    "https://www.linkedin.com/jobs/search?"
    "trk=guest_homepage-basic_guest_nav_menu_jobs"
)
URL_TEST_CONNECTION = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/"
    "search?trk=guest_homepage-basic_guest_nav_menu_jobs&start=0"
)
URL_LOG_IN = "https://www.linkedin.com/checkpoint/lg/login-submit"

URL_PARAM_KEYWORDS = "keywords"
URL_PARAM_N_SECONDS = "n_seconds"
URL_PARAM_N_DAYS = "n_days"
URL_PARAM_LOCATION = "location"
URL_PARAM_GEO_ID = "geo_id"
URL_PARAM_WORK_LOCATION = "work_location"

URL_FOR_N_JOBS = (
    f"https://www.linkedin.com/jobs/search?"
    f"keywords={{{URL_PARAM_KEYWORDS}}}&"
    f"f_TPR=r{{{URL_PARAM_N_SECONDS}}}&"
    f"location={{{URL_PARAM_LOCATION}}}&"
    f"geoId={{{URL_PARAM_GEO_ID}}}&"
    f"f_WT={{{URL_PARAM_WORK_LOCATION}}}"
)
URL_JOB_PAGE = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
    f"keywords={{{URL_PARAM_KEYWORDS}}}&"
    f"f_TPR=r{{{URL_PARAM_N_SECONDS}}}&"
    f"location={{{URL_PARAM_LOCATION}}}&"
    f"geoId={{{URL_PARAM_GEO_ID}}}&"
    f"f_WT={{{URL_PARAM_WORK_LOCATION}}}&"
    "start={start}"
)
URL_SINGLE_JOB = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"


# HTML stuff
HTML_JOB_TITLE = """
<h1 class="title">    
    <a class="hidden-nested-link" href="{link}">{title} at {company}, {location}</a>
</h1>\n
"""
HTML_JOB_SEPARATOR = f"\n{'-':-<500}\n"
