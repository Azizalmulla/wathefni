"""Entitlement/permission regression for workspace composition authority."""

from __future__ import annotations

from workspace_capability import COMPOSITION_MATRIX, authority_fixture_for_matrix_row, resolve_workspace_authority


def test_composition_matrix():
    for row in COMPOSITION_MATRIX:
        authority = resolve_workspace_authority(row["modules"], row["role"])
        nav = set(authority["nav_ids"])
        assert authority["nav_groups"] == row["expect_nav_groups"], row["id"]
        for page in row["expect_nav_includes"]:
            assert page in nav, f"{row['id']}: missing {page} in {sorted(nav)}"
        for page in row["expect_nav_excludes"]:
            assert page not in nav, f"{row['id']}: unexpected {page} in {sorted(nav)}"
        assert authority["overview_layout"] == row["expect_overview_layout"], row["id"]
        # Empty groups never emitted
        assert all(g["ids"] for g in authority["nav_group_detail"]), row["id"]


def test_recruiter_vs_owner_permission_regression():
    owner = resolve_workspace_authority(
        ["pre_hiring", "assessments", "interviews", "video_interviews", "calendar"],
        "owner",
    )
    recruiter = resolve_workspace_authority(
        ["pre_hiring", "assessments", "interviews", "leave", "payroll"],
        "recruiter",
    )
    assert "overview" in owner["nav_ids"]
    assert "overview" not in recruiter["nav_ids"]
    assert "ai" not in recruiter["nav_ids"]
    assert "assessments" not in recruiter["nav_ids"]
    assert "payroll" not in recruiter["nav_ids"]
    assert recruiter["overview_layout"] == "two"
    assert owner["offerable"]["tab.interviews.video"] is True


def test_video_tab_requires_module():
    with_video = resolve_workspace_authority(["pre_hiring", "interviews", "video_interviews"], "owner")
    without = resolve_workspace_authority(["pre_hiring", "interviews"], "owner")
    assert with_video["offerable"]["tab.interviews.video"] is True
    assert without["offerable"]["tab.interviews.video"] is False


def test_interviews_nav_not_offered_for_bare_pre_hiring():
    prehire_only = resolve_workspace_authority(["pre_hiring"], "owner")
    video_only = resolve_workspace_authority(["pre_hiring", "video_interviews"], "owner")
    assert "interviews" not in prehire_only["nav_ids"]
    assert "assessments" not in prehire_only["nav_ids"]
    assert "interviews" in video_only["nav_ids"]


def test_assessments_nav_requires_module():
    off = resolve_workspace_authority(["pre_hiring", "interviews"], "owner")
    on = resolve_workspace_authority(["pre_hiring", "assessments"], "owner")
    assert "assessments" not in off["nav_ids"]
    assert "assessments" in on["nav_ids"]


def test_visual_fixtures_shape():
    fixtures = [authority_fixture_for_matrix_row(row) for row in COMPOSITION_MATRIX]
    assert len(fixtures) == len(COMPOSITION_MATRIX)
    assert all("nav_ids" in f and "overview_layout" in f for f in fixtures)


if __name__ == "__main__":
    test_composition_matrix()
    test_recruiter_vs_owner_permission_regression()
    test_video_tab_requires_module()
    test_interviews_nav_not_offered_for_bare_pre_hiring()
    test_assessments_nav_requires_module()
    test_visual_fixtures_shape()
    print("workspace composition matrix PASS")
