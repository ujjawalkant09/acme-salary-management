from app.core.rate_limit import limiter

API = "/api/v1/insights"


def make_group(make_employee, salaries, **fields):
    return [make_employee(salary=s, **fields) for s in salaries]


def test_summary_numbers(admin_client, make_employee, db):
    make_group(make_employee, ["100000", "120000"])
    make_employee(country_code="IN", salary="1000000")  # 12,000 USD
    gone = make_employee(salary="500000")
    gone.status = "left"
    db.commit()
    body = admin_client.get(f"{API}/summary").json()
    assert body["headcount"] == 3
    assert body["payroll_usd"] == "232000.00"
    assert body["median_salary_usd"] == "100000.00"
    assert body["countries"] == 2
    assert body["rates_date"] == "2026-10-14"


def test_summary_counts_upcoming_changes_in_next_7_days(admin_client, make_employee):
    e = make_employee()
    admin_client.post(f"/api/v1/employees/{e.id}/salaries",
                      json={"version": 1, "amount": "1", "effective_date": "2026-10-20", "reason": "merit"})  # fmt: skip
    assert admin_client.get(f"{API}/summary").json()["upcoming_changes_7d"] == 1


def test_empty_database(admin_client):
    body = admin_client.get(f"{API}/summary").json()
    assert (body["headcount"], body["payroll_usd"], body["median_salary_usd"]) == (
        0,
        "0.00",
        "0.00",
    )
    assert admin_client.get(f"{API}/by-country").json()["groups"] == []
    assert admin_client.get(f"{API}/distribution").json()["bins"] == []
    assert admin_client.get(f"{API}/outliers").json()["total"] == 0


def test_by_country_is_local_with_usd_for_comparison(admin_client, make_employee):
    make_group(make_employee, ["1000000", "2000000", "3000000"], country_code="IN")
    make_employee(country_code="US", salary="100000")
    groups = {g["key"]: g for g in admin_client.get(f"{API}/by-country").json()["groups"]}
    india = groups["IN"]
    assert (india["label"], india["currency"], india["people"]) == ("India", "INR", 3)
    assert (india["median"], india["cost"]) == ("2000000.00", "6000000.00")
    assert (india["median_usd"], india["cost_usd"]) == ("24000.00", "72000.00")
    assert groups["US"]["median"] == "100000.00"


def test_by_department_in_usd(admin_client, make_employee):
    make_employee(department_id=2, salary="50000")
    make_employee(department_id=2, country_code="IN", salary="5000000")  # 60,000 USD
    group = admin_client.get(f"{API}/by-department").json()["groups"][0]
    assert (group["label"], group["currency"], group["median"]) == ("Sales", "USD", "55000.00")


def test_by_role_within_one_country_with_outliers(admin_client, make_employee):
    make_group(make_employee, ["100000", "102000", "104000", "106000", "300000"])
    make_employee(job_level=4, salary="150000")
    groups = admin_client.get(f"{API}/by-role", params={"country": "US"}).json()["groups"]
    assert [(g["label"], g["job_level"], g["people"], g["outliers"]) for g in groups] == [
        ("Software Engineer", 3, 5, 1),
        ("Software Engineer", 4, 1, 0),
    ]


def test_by_role_needs_a_known_country(admin_client):
    assert admin_client.get(f"{API}/by-role").status_code == 422
    assert admin_client.get(f"{API}/by-role", params={"country": "FR"}).status_code == 404
    assert admin_client.get(f"{API}/by-role", params={"country": "us"}).status_code == 422


def test_outliers_listed_biggest_difference_first(admin_client, make_employee):
    make_group(make_employee, ["100000", "100000", "102000", "104000"])
    high = make_employee(salary="300000")
    low = make_employee(salary="20000")
    page = admin_client.get(f"{API}/outliers").json()
    assert [(i["employee_id"], i["direction"]) for i in page["items"]] == [
        (high.id, "above"),
        (low.id, "below"),
    ]
    assert page["items"][0]["peer_count"] == 6
    assert admin_client.get(f"{API}/outliers", params={"country": "IN"}).json()["total"] == 0
    assert admin_client.get(f"{API}/outliers", params={"page_size": 101}).status_code == 422


def test_outliers_only_filter_in_people_list(admin_client, make_employee):
    make_group(make_employee, ["100000", "100000", "102000", "104000"])
    high = make_employee(salary="300000")
    body = admin_client.get("/api/v1/employees", params={"outliers_only": True}).json()
    assert [e["id"] for e in body["items"]] == [high.id]


def test_distribution_bins(admin_client, make_employee):
    make_group(make_employee, ["100000", "150000", "200000"])
    body = admin_client.get(f"{API}/distribution", params={"bins": 2}).json()
    assert body["currency"] == "USD"
    assert [b["count"] for b in body["bins"]] == [1, 2]
    assert admin_client.get(f"{API}/distribution", params={"bins": 1}).status_code == 422
    local = admin_client.get(f"{API}/distribution", params={"country": "US"}).json()
    assert local["currency"] == "USD" and len(local["bins"]) == 20


def test_numbers_update_right_after_a_change(admin_client, make_employee):
    e = make_employee(salary="100000")
    assert admin_client.get(f"{API}/summary").json()["payroll_usd"] == "100000.00"
    admin_client.post(f"/api/v1/employees/{e.id}/salaries",
                      json={"version": 1, "amount": "150000", "effective_date": "2026-10-01", "reason": "merit"})  # fmt: skip
    assert admin_client.get(f"{API}/summary").json()["payroll_usd"] == "150000.00"


def test_etag_gives_304_until_data_changes(admin_client, make_employee):
    e = make_employee()
    first = admin_client.get(f"{API}/by-country")
    etag = first.headers["ETag"]
    cached = admin_client.get(f"{API}/by-country", headers={"If-None-Match": etag})
    assert cached.status_code == 304 and cached.content == b""
    admin_client.patch(f"/api/v1/employees/{e.id}", json={"version": 1, "city": "Austin"})
    changed = admin_client.get(f"{API}/by-country", headers={"If-None-Match": etag})
    assert changed.status_code == 200 and changed.headers["ETag"] != etag


def test_insights_are_rate_limited_per_user(admin_client, viewer_client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    codes = [admin_client.get(f"{API}/by-department").status_code for _ in range(61)]
    assert codes[:60] == [200] * 60 and codes[60] == 429
    # Another user has their own allowance.
    assert viewer_client.get(f"{API}/by-department").status_code == 200
