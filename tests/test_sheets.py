from datetime import date, datetime
import gspread

from scraper import HEADER, WIB, JobPosting, SheetsSync

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=WIB)


class FakeWorksheet:
    def __init__(self, title: str, rows: list[list[str]] | None = None) -> None:
        self.title = title
        self.rows: list[list[str]] = [list(r) for r in (rows or [])]
        self.append_rows_calls: list[tuple[list[list[str]], str | None]] = []

    def get_all_values(self) -> list[list[str]]:
        return [list(r) for r in self.rows]

    def append_row(self, values: list[str], value_input_option: str | None = None) -> None:
        self.rows.append(list(values))

    def append_rows(
        self,
        values: list[list[str]],
        value_input_option: str | None = None,
    ) -> None:
        self.append_rows_calls.append(([list(r) for r in values], value_input_option))
        for r in values:
            self.rows.append(list(r))

    def clear(self) -> None:
        self.rows.clear()

    def update(self, values: list[list[str]], value_input_option: str | None = None) -> None:
        self.rows = [list(r) for r in values]

    def resize(self, rows: int | None = None, cols: int | None = None) -> None:
        pass


class FakeSpreadsheet:
    def __init__(self, worksheets: dict[str, FakeWorksheet] | None = None) -> None:
        self._worksheets: dict[str, FakeWorksheet] = worksheets or {}

    def worksheet(self, title: str) -> FakeWorksheet:
        if title not in self._worksheets:
            raise gspread.WorksheetNotFound(title)
        return self._worksheets[title]

    def add_worksheet(self, title: str, rows: int, cols: int) -> FakeWorksheet:
        ws = FakeWorksheet(title)
        self._worksheets[title] = ws
        return ws


def test_sync_creates_worksheet_and_header():
    sp = FakeSpreadsheet()
    syncer = SheetsSync(sp, sheet_name="Job_Tracker")
    ws = sp.worksheet("Job_Tracker")
    assert ws.rows == [HEADER]
    assert syncer.existing_urls() == set()


def test_sync_skips_existing_normalized_url():
    existing_row = [
        "2026-11-11 09:00:00",
        "System Analyst",
        "System Analyst",
        "PT Elnusa Tbk",
        "Jakarta, Indonesia",
        "LinkedIn",
        "2026-11-05",
        "Entry/Fresh Graduate",
        "https://id.linkedin.com/jobs/view/system-analyst-at-pt-elnusa-tbk-4487719677?position=1&refId=abc",
        "Applied",
    ]
    ws = FakeWorksheet("Job_Tracker", rows=[HEADER, existing_row])
    sp = FakeSpreadsheet({"Job_Tracker": ws})
    syncer = SheetsSync(sp, sheet_name="Job_Tracker")

    dup_posting = JobPosting(
        title="System Analyst",
        company="PT Elnusa Tbk",
        location="Jakarta, Indonesia",
        platform="LinkedIn",
        url="https://www.linkedin.com/jobs/view/4487719677",
        date_posted=date(2026, 11, 5),
        experience_level="Entry/Fresh Graduate",
        role_category="System Analyst",
    )
    added = syncer.sync([dup_posting], NOW)
    assert added == 0
    assert ws.append_rows_calls == []


def test_sync_appends_in_single_batch():
    ws = FakeWorksheet("Job_Tracker", rows=[HEADER])
    sp = FakeSpreadsheet({"Job_Tracker": ws})
    syncer = SheetsSync(sp, sheet_name="Job_Tracker")

    postings = [
        JobPosting(
            title=f"IoT Engineer {i}",
            company="PT X",
            location="Bandung",
            platform="Jobstreet",
            url=f"https://id.jobstreet.com/id/job/{100 + i}",
            date_posted=date(2026, 11, 10),
            role_category="IoT Engineer",
        )
        for i in range(3)
    ]
    added = syncer.sync(postings, NOW)
    assert added == 3
    assert len(ws.append_rows_calls) == 1
    rows_arg, opt_arg = ws.append_rows_calls[0]
    assert len(rows_arg) == 3
    assert opt_arg == "RAW"


def test_sync_does_not_touch_existing_rows():
    existing_row = [
        "2026-11-10 08:00:00",
        "System Analyst",
        "System Analyst",
        "PT A",
        "Jakarta",
        "Jobstreet",
        "2026-11-09",
        "Junior",
        "https://id.jobstreet.com/id/job/111",
        "Applied",
    ]
    ws = FakeWorksheet("Job_Tracker", rows=[HEADER, existing_row])
    sp = FakeSpreadsheet({"Job_Tracker": ws})
    syncer = SheetsSync(sp, sheet_name="Job_Tracker")

    new_posting = JobPosting(
        title="IoT Engineer",
        company="PT B",
        location="Bekasi",
        platform="Glints",
        url="https://glints.com/id/opportunities/jobs/iot-engineer/222",
        date_posted=date(2026, 11, 11),
        role_category="IoT Engineer",
    )
    added = syncer.sync([new_posting], NOW)
    assert added == 1
    assert ws.rows[1] == existing_row
    assert ws.rows[1][9] == "Applied"
    assert ws.rows[2][9] == "New"


def test_migrates_legacy_9_column_sheet_without_data_loss():
    legacy_header = [
        "Timestamp_Scraped",
        "Job_Title",
        "Company",
        "Location",
        "Platform",
        "Date_Posted",
        "Experience_Level",
        "Job_URL",
        "Status",
    ]
    legacy_row_1 = [
        "2026-11-10 08:00:00",
        "Junior System Analyst",
        "PT A",
        "Jakarta",
        "Jobstreet",
        "2026-11-09",
        "Junior",
        "https://id.jobstreet.com/id/job/111",
        "Applied",
    ]
    legacy_row_2 = [
        "2026-11-10 08:05:00",
        "Hardware & IoT Engineer",
        "PT B",
        "Bandung",
        "LinkedIn",
        "2026-11-08",
        "Entry/Fresh Graduate",
        "https://www.linkedin.com/jobs/view/222",
        "Interview",
    ]
    ws = FakeWorksheet("Job_Tracker", rows=[legacy_header, legacy_row_1, legacy_row_2])
    sp = FakeSpreadsheet({"Job_Tracker": ws})
    syncer = SheetsSync(sp, sheet_name="Job_Tracker")

    assert ws.rows[0] == HEADER
    assert len(ws.rows) == 3
    assert ws.rows[1] == [
        "2026-11-10 08:00:00",
        "System Analyst",
        "Junior System Analyst",
        "PT A",
        "Jakarta",
        "Jobstreet",
        "2026-11-09",
        "Junior",
        "https://id.jobstreet.com/id/job/111",
        "Applied",
    ]
    assert ws.rows[2] == [
        "2026-11-10 08:05:00",
        "IoT Engineer",
        "Hardware & IoT Engineer",
        "PT B",
        "Bandung",
        "LinkedIn",
        "2026-11-08",
        "Entry/Fresh Graduate",
        "https://www.linkedin.com/jobs/view/222",
        "Interview",
    ]
    assert syncer.existing_urls() == {
        "https://id.jobstreet.com/id/job/111",
        "https://www.linkedin.com/jobs/view/222",
    }
