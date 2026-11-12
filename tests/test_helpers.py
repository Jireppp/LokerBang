from datetime import date, datetime
import pytest

from scraper import (
    WIB,
    JobPosting,
    ROLES,
    classify_experience,
    infer_role_category,
    is_within_days,
    match_location,
    match_title,
    normalize_url,
    parse_relative_date,
    passes_role_a_seniority,
)

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=WIB)


def test_parse_relative_date_en():
    assert parse_relative_date("3 days ago", NOW) == date(2026, 11, 9)
    assert parse_relative_date("2 hours ago", NOW) == date(2026, 11, 12)
    assert parse_relative_date("1 week ago", NOW) == date(2026, 11, 5)
    assert parse_relative_date("2026-11-05", NOW) == date(2026, 11, 5)
    assert parse_relative_date("2026-11-05T08:31:23Z", NOW) == date(2026, 11, 5)
    assert parse_relative_date("Just now", NOW) == date(2026, 11, 12)
    assert parse_relative_date("Yesterday", NOW) == date(2026, 11, 11)


def test_parse_relative_date_id_phrases():
    assert parse_relative_date("6 hari yang lalu", NOW) == date(2026, 11, 6)
    assert parse_relative_date("2 jam yang lalu", NOW) == date(2026, 11, 12)
    assert parse_relative_date("1 minggu yang lalu", NOW) == date(2026, 11, 5)
    assert parse_relative_date("kemarin", NOW) == date(2026, 11, 11)
    assert parse_relative_date("hari ini", NOW) == date(2026, 11, 12)
    assert parse_relative_date("baru saja", NOW) == date(2026, 11, 12)
    assert parse_relative_date("30+ hari yang lalu", NOW) == date(2026, 10, 13)
    assert parse_relative_date("garbage text ???", NOW) is None
    assert parse_relative_date("", NOW) is None


def test_is_within_days():
    assert is_within_days(date(2026, 11, 5), NOW, 14) is True
    assert is_within_days(date(2026, 10, 29), NOW, 14) is True  # exactly 14 days
    assert is_within_days(date(2026, 10, 28), NOW, 14) is False  # 15 days
    assert is_within_days(None, NOW, 14) is False


def test_match_location():
    assert match_location("Jakarta Selatan, Jakarta Raya") is True
    assert match_location("Bekasi, Jawa Barat") is True
    assert match_location("Kota Bandung, Jawa Barat") is True
    assert match_location("Tangerang Selatan, Banten") is True
    assert match_location("BSD City, Tangerang") is True
    assert match_location("Cikarang, Bekasi") is True
    assert match_location("Depok, Jawa Barat") is True
    assert match_location("Bogor, Jawa Barat") is True
    assert match_location("Cimahi, Jawa Barat") is False
    assert match_location("Bandung Barat, Jawa Barat") is False
    assert match_location("Kabupaten Bandung Barat") is False
    assert match_location("Surabaya, Jawa Timur") is False
    assert match_location("Indonesia") is False
    assert match_location("") is False


def test_match_title():
    assert set(ROLES.keys()) == {
        "system_analyst",
        "iot_engineer",
        "it_support",
        "product_support",
        "technical_writer",
    }
    sa = ROLES["system_analyst"]
    iot = ROLES["iot_engineer"]
    its = ROLES["it_support"]
    ps = ROLES["product_support"]
    tw = ROLES["technical_writer"]

    assert sa.queries == [
        "System Analyst",
        "Junior System Analyst",
        "IT Business Analyst",
        "Functional Analyst",
    ]
    assert iot.queries == [
        "IoT Engineer",
        "Internet of Things Engineer",
        "Embedded Engineer",
        "Automation & IoT",
    ]
    assert its.queries == [
        "IT Support",
        "IT Helpdesk",
        "Technical Support",
        "Desktop Support",
    ]
    assert ps.queries == [
        "Product Support",
        "Application Support",
        "SaaS Support",
        "Product Operations Support",
    ]
    assert tw.queries == [
        "Technical Writer",
        "Product Technical Writer",
        "IT Documentation Specialist",
        "Technical Content Writer",
    ]

    assert match_title("Junior System Analyst", sa) is True
    assert match_title("Analis Sistem Informasi", sa) is True
    assert match_title("IT Business Analyst", sa) is True
    assert match_title("Functional Analyst", sa) is True
    assert match_title("System Analyst & Design", sa) is True
    assert match_title("Data Analyst", sa) is False

    assert match_title("IoT Engineer", iot) is True
    assert match_title("Internet of Things Engineer", iot) is True
    assert match_title("Embedded Engineer", iot) is True
    assert match_title("Automation & IoT Specialist", iot) is True
    assert match_title("Hardware Sales Executive", iot) is False

    assert match_title("IT Support Specialist", its) is True
    assert match_title("IT Helpdesk Officer", its) is True
    assert match_title("Technical Support Engineer", its) is True
    assert match_title("Desktop Support", its) is True

    assert match_title("Product Support Specialist", ps) is True
    assert match_title("Application Support Engineer", ps) is True
    assert match_title("SaaS Support Specialist", ps) is True
    assert match_title("Product Operations Support", ps) is True

    assert match_title("Technical Writer", tw) is True
    assert match_title("Product Technical Writer", tw) is True
    assert match_title("IT Documentation Specialist", tw) is True
    assert match_title("Technical Content Writer", tw) is True

    assert infer_role_category("Junior System Analyst") == "System Analyst"
    assert infer_role_category("Embedded & IoT Engineer") == "IoT Engineer"
    assert infer_role_category("IT Helpdesk Support") == "IT Support"
    assert infer_role_category("Application Support Engineer") == "Product Support"
    assert infer_role_category("Technical Writer") == "Technical Writer"


def test_role_a_seniority_filter():
    assert passes_role_a_seniority("Senior System Analyst", "Not specified") is False
    assert passes_role_a_seniority("System Analyst Lead", "Not specified") is False
    assert passes_role_a_seniority("System Analyst Manager", "Not specified") is False
    assert passes_role_a_seniority("Sr. System Analyst", "Not specified") is False
    assert passes_role_a_seniority("System Analyst", "Senior") is False
    assert passes_role_a_seniority("System Analyst", "Lead/Manager") is False
    assert passes_role_a_seniority("System Analyst", "3-5 yrs") is False
    assert passes_role_a_seniority("System Analyst", "5+ yrs") is False
    assert passes_role_a_seniority("System Analyst", "5 tahun") is False
    assert passes_role_a_seniority("System Analyst (Min. 5 Tahun)", "Entry/Junior (LinkedIn filter)") is False
    assert (
        passes_role_a_seniority(
            "Staff System Analyst",
            classify_experience("Staff System Analyst minimal 5 tahun"),
        )
        is False
    )
    assert passes_role_a_seniority("System Analyst", "Not specified") is True
    assert passes_role_a_seniority("Junior System Analyst", "Junior") is True
    assert passes_role_a_seniority("System Analyst (Fresh Graduate)", "Entry/Fresh Graduate") is True
    assert passes_role_a_seniority("System Analyst", "0-2 yrs") is True
    assert passes_role_a_seniority("System Analyst", "1-3 yrs") is True


def test_classify_experience():
    assert classify_experience("Fresh Graduate welcome") == "Entry/Fresh Graduate"
    assert classify_experience("Entry level") == "Entry/Fresh Graduate"
    assert classify_experience("Junior / Associate") == "Junior"
    assert classify_experience("Mid-Senior level") == "Senior"
    assert classify_experience("Lead / Manager") == "Lead/Manager"
    assert classify_experience("Minimal pengalaman 1-3 tahun") == "1-3 yrs"
    assert classify_experience("") == "Not specified"


def test_normalize_url_strips_tracking():
    li = (
        "https://id.linkedin.com/jobs/view/"
        "system-analyst-at-pt-elnusa-tbk-4487719677"
        "?position=1&pageNum=0&refId=abc&trackingId=xyz"
    )
    assert normalize_url(li) == "https://www.linkedin.com/jobs/view/4487719677"
    li2 = "https://www.linkedin.com/jobs/view/4487719677/"
    assert normalize_url(li2) == "https://www.linkedin.com/jobs/view/4487719677"

    js = "https://id.jobstreet.com/id/job/95720018?type=standard&ref=search-standalone#sol=abc"
    assert normalize_url(js) == "https://id.jobstreet.com/id/job/95720018"

    gl = "https://glints.com/id/opportunities/jobs/iot-engineer/abc-123?utm_source=x"
    assert normalize_url(gl) == "https://glints.com/id/opportunities/jobs/iot-engineer/abc-123"

    ind = "https://id.indeed.com/viewjob?jk=e933db10b1ec15d8&tk=1h234&from=serp"
    assert normalize_url(ind) == "https://id.indeed.com/viewjob?jk=e933db10b1ec15d8"


def test_job_posting_to_row():
    p = JobPosting(
        title="System Analyst",
        company="PT Elnusa Tbk",
        location="Jakarta, Indonesia",
        platform="LinkedIn",
        url="https://www.linkedin.com/jobs/view/4487719677",
        date_posted=date(2026, 11, 5),
        experience_level="Entry/Fresh Graduate",
        role_category="System Analyst",
    )
    row = p.to_row(NOW)
    assert row == [
        "2026-11-12 10:00:00",
        "System Analyst",
        "System Analyst",
        "PT Elnusa Tbk",
        "Jakarta, Indonesia",
        "LinkedIn",
        "2026-11-05",
        "Entry/Fresh Graduate",
        "https://www.linkedin.com/jobs/view/4487719677",
        "New",
    ]
    p_no_date = JobPosting(
        title="IoT Engineer",
        company="PT X",
        location="Bandung",
        platform="Jobstreet",
        url="https://id.jobstreet.com/id/job/1",
        date_posted=None,
    )
    assert p_no_date.to_row(NOW)[1] == "IoT Engineer"
    assert p_no_date.to_row(NOW)[6] == ""
    assert p_no_date.to_row(NOW)[7] == "Not specified"
