"""Tests for jobs router: GET /jobs, GET /jobs/{id}."""
from src.models import Job, JobMatch, UserPreferences


class TestListJobs:
    def test_returns_empty_list_when_no_jobs(self, client):
        resp = client.get("/jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_jobs_with_match_scores(self, client, db_session, test_user):
        job = Job(title="Backend Engineer", company="Acme", source="test")
        db_session.add(job)
        db_session.commit()

        match = JobMatch(
            job_id=job.id,
            user_id=test_user.id,
            match_score=75.0,
            skill_score=30.0,
        )
        db_session.add(match)
        db_session.commit()

        resp = client.get("/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Backend Engineer"
        assert data[0]["match"]["match_score"] == 75.0
        assert data[0]["match"]["skill_score"] == 30.0

    def test_match_is_none_when_no_job_match_row(self, client, db_session):
        job = Job(title="Designer", company="Corp", source="test")
        db_session.add(job)
        db_session.commit()

        # sort=date avoids the JobMatch JOIN so jobs without scores are included
        resp = client.get("/jobs?sort=date")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["match"] is None

    def test_keyword_filter_matches_title(self, client, db_session):
        db_session.add_all(
            [
                Job(title="Backend Engineer", company="A", source="test"),
                Job(title="UX Designer", company="B", source="test"),
            ]
        )
        db_session.commit()

        resp = client.get("/jobs?keywords=backend&sort=date")
        assert resp.status_code == 200
        titles = [j["title"] for j in resp.json()]
        assert "Backend Engineer" in titles
        assert "UX Designer" not in titles

    def test_location_filter(self, client, db_session):
        db_session.add_all(
            [
                Job(title="Job A", company="X", source="test", location="Berlin"),
                Job(title="Job B", company="Y", source="test", location="London"),
            ]
        )
        db_session.commit()

        resp = client.get("/jobs?location=Berlin")
        assert resp.status_code == 200
        locations = [j["location"] for j in resp.json()]
        assert all(loc == "Berlin" for loc in locations)

    def test_pagination_page_size(self, client, db_session):
        for i in range(5):
            db_session.add(Job(title=f"Job {i}", company="Corp", source="test"))
        db_session.commit()

        resp = client.get("/jobs?page=1&page_size=2&sort=date")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_pagination_page_2(self, client, db_session):
        for i in range(5):
            db_session.add(Job(title=f"Job {i}", company="Corp", source="test"))
        db_session.commit()

        page1 = client.get("/jobs?page=1&page_size=3&sort=date").json()
        page2 = client.get("/jobs?page=2&page_size=3&sort=date").json()
        assert len(page2) == 2
        ids_p1 = {j["id"] for j in page1}
        ids_p2 = {j["id"] for j in page2}
        assert ids_p1.isdisjoint(ids_p2)

    def test_inactive_jobs_excluded(self, client, db_session):
        db_session.add_all(
            [
                Job(title="Active Role", company="A", source="test"),
                Job(title="Closed Role", company="B", source="test", is_active=False),
            ]
        )
        db_session.commit()

        resp = client.get("/jobs?sort=date")
        assert resp.status_code == 200
        titles = [j["title"] for j in resp.json()]
        assert "Active Role" in titles
        assert "Closed Role" not in titles

    def test_unauthenticated_returns_4xx(self, auth_client):
        resp = auth_client.get("/jobs")
        assert resp.status_code in (401, 403)

    def test_remote_filter_excludes_ineligible_countries(
        self, client, db_session, test_user
    ):
        """Remote jobs from countries not in user's preferred_countries are hidden."""
        prefs = UserPreferences(
            user_id=test_user.id,
            preferred_countries=["GB", "ES"],
        )
        db_session.add(prefs)
        db_session.add_all(
            [
                # eligible — country matches
                Job(
                    title="UK Remote",
                    company="A",
                    source="test",
                    remote="remote",
                    country="gb",
                ),
                # eligible — no country restriction (global ATS role)
                Job(
                    title="Global Remote",
                    company="B",
                    source="test",
                    remote="remote",
                    country=None,
                ),
                # ineligible — wrong country
                Job(
                    title="US Remote",
                    company="C",
                    source="test",
                    remote="remote",
                    country="us",
                ),
            ]
        )
        db_session.commit()

        resp = client.get("/jobs?remote=remote&sort=date")
        assert resp.status_code == 200
        titles = {j["title"] for j in resp.json()}
        assert "UK Remote" in titles
        assert "Global Remote" in titles
        assert "US Remote" not in titles

    def test_remote_filter_no_restriction_when_no_preferred_countries(
        self, client, db_session, test_user
    ):
        """Without preferred_countries set, all remote jobs are shown."""
        # test_user has no UserPreferences — no country restriction applied
        db_session.add_all(
            [
                Job(
                    title="US Remote",
                    company="A",
                    source="test",
                    remote="remote",
                    country="us",
                ),
                Job(
                    title="UK Remote",
                    company="B",
                    source="test",
                    remote="remote",
                    country="gb",
                ),
            ]
        )
        db_session.commit()

        resp = client.get("/jobs?remote=remote&sort=date")
        assert resp.status_code == 200
        titles = {j["title"] for j in resp.json()}
        assert "US Remote" in titles
        assert "UK Remote" in titles

    def test_country_filter_not_applied_for_onsite(self, client, db_session, test_user):
        """Country eligibility filter does not apply to non-remote searches."""
        prefs = UserPreferences(
            user_id=test_user.id,
            preferred_countries=["GB"],
        )
        db_session.add(prefs)
        db_session.add(
            Job(
                title="US Onsite",
                company="A",
                source="test",
                remote="onsite",
                country="us",
            )
        )
        db_session.commit()

        resp = client.get("/jobs?remote=onsite&sort=date")
        assert resp.status_code == 200
        titles = {j["title"] for j in resp.json()}
        assert "US Onsite" in titles

    # ── Regression: onsite filter with null remote ────────────────────────────

    def test_onsite_filter_includes_null_remote_jobs(self, client, db_session):
        """remote=onsite must surface jobs where remote is NULL, not just tagged 'onsite'.

        Regression: filter used Job.remote=='onsite' which matched almost nothing  # noqa: E501
        because onsite jobs are rarely tagged — they just have remote=NULL.
        """
        db_session.add_all(
            [
                Job(
                    title="Office Role",
                    company="A",
                    source="test",
                    remote=None,
                    location="Gibraltar",
                ),
                Job(
                    title="Remote Role",
                    company="B",
                    source="test",
                    remote="remote",
                    location="Gibraltar",
                ),
                Job(
                    title="Hybrid Role",
                    company="C",
                    source="test",
                    remote="hybrid",
                    location="Gibraltar",
                ),
            ]
        )
        db_session.commit()

        resp = client.get("/jobs?remote=onsite&location=Gibraltar&sort=date")
        assert resp.status_code == 200
        titles = {j["title"] for j in resp.json()}
        assert "Office Role" in titles
        assert "Remote Role" not in titles
        assert "Hybrid Role" not in titles

    # ── Regression: location fallback uses all preferred locations ────────────

    def test_onsite_uses_all_preferred_locations_not_just_first(
        self, client, db_session, test_user
    ):
        """remote=onsite without explicit location must OR all preferred_locations.

        Regression: router injected only preferred_locations[0] ('Malaga'),
        so jobs in Gibraltar (index 2) were silently excluded.
        """
        prefs = UserPreferences(
            user_id=test_user.id,
            preferred_locations=["Malaga", "Cadiz", "Gibraltar"],
            remote_preference="onsite",
        )
        db_session.add(prefs)
        db_session.add_all(
            [
                Job(
                    title="Malaga Job",
                    company="A",
                    source="test",
                    location="Malaga",
                    remote=None,
                ),
                Job(
                    title="Gibraltar Job",
                    company="B",
                    source="test",
                    location="Gibraltar",
                    remote=None,
                ),
                Job(
                    title="Berlin Job",
                    company="C",
                    source="test",
                    location="Berlin",
                    remote=None,
                ),
            ]
        )
        db_session.commit()

        # No explicit location param — router should fall back to all prefs
        resp = client.get("/jobs?remote=onsite&sort=date")
        assert resp.status_code == 200
        titles = {j["title"] for j in resp.json()}
        assert "Malaga Job" in titles
        assert "Gibraltar Job" in titles
        assert "Berlin Job" not in titles


class TestGetJob:
    def test_returns_job_detail(self, client, db_session):
        job = Job(
            title="SRE",
            company="BigCo",
            source="test",
            description="Keep the lights on",
            location="Remote",
        )
        db_session.add(job)
        db_session.commit()

        resp = client.get(f"/jobs/{job.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "SRE"
        assert data["description"] == "Keep the lights on"
        assert data["location"] == "Remote"

    def test_attaches_match_score_for_current_user(self, client, db_session, test_user):
        job = Job(title="SRE", company="BigCo", source="test")
        db_session.add(job)
        db_session.commit()

        match = JobMatch(
            job_id=job.id,
            user_id=test_user.id,
            match_score=90.0,
            title_score=25.0,
        )
        db_session.add(match)
        db_session.commit()

        resp = client.get(f"/jobs/{job.id}")
        assert resp.status_code == 200
        assert resp.json()["match"]["match_score"] == 90.0

    def test_match_is_none_when_no_match_row(self, client, db_session):
        job = Job(title="PM", company="Corp", source="test")
        db_session.add(job)
        db_session.commit()

        resp = client.get(f"/jobs/{job.id}")
        assert resp.status_code == 200
        assert resp.json()["match"] is None

    def test_returns_404_for_unknown_job(self, client):
        resp = client.get("/jobs/99999")
        assert resp.status_code == 404

    def test_match_is_scoped_to_current_user(self, client, db_session, test_user):
        """A different user's JobMatch should not appear for the test user."""
        from src.models import User

        other = User(
            google_id="other-111",
            email="other@example.com",
            name="Other",
        )
        db_session.add(other)
        db_session.commit()

        job = Job(title="Analyst", company="Corp", source="test")
        db_session.add(job)
        db_session.commit()

        # Only add a match for 'other', not for test_user
        match = JobMatch(job_id=job.id, user_id=other.id, match_score=55.0)
        db_session.add(match)
        db_session.commit()

        resp = client.get(f"/jobs/{job.id}")
        assert resp.status_code == 200
        assert resp.json()["match"] is None
