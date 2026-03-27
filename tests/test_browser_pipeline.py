from raidbot.browser.models import (
    RaidActionJob,
    RaidActionRequirements,
    RaidDetectionResult,
    RaidExecutionResult,
)
from raidbot.models import (
    RaidActionJob as SharedRaidActionJob,
    RaidActionRequirements as SharedRaidActionRequirements,
    RaidDetectionResult as SharedRaidDetectionResult,
    RaidExecutionResult as SharedRaidExecutionResult,
)


def build_job() -> RaidActionJob:
    return RaidActionJob(
        normalized_url="https://x.com/i/status/123",
        raw_url="https://x.com/i/status/123",
        chat_id=-1001,
        sender_id=42,
        requirements=RaidActionRequirements(
            like=True,
            repost=True,
            bookmark=False,
            reply=True,
        ),
        preset_replies=("gm",),
        trace_id="raid-1",
    )


def test_raid_action_requirements_tracks_requested_actions() -> None:
    requirements = RaidActionRequirements(
        like=True,
        repost=False,
        bookmark=True,
        reply=False,
    )

    assert requirements.like is True
    assert requirements.repost is False
    assert requirements.bookmark is True
    assert requirements.reply is False


def test_raid_action_job_carries_browser_handoff_context() -> None:
    job = build_job()

    assert job.normalized_url == "https://x.com/i/status/123"
    assert job.raw_url == "https://x.com/i/status/123"
    assert job.chat_id == -1001
    assert job.sender_id == 42
    assert job.requirements == RaidActionRequirements(
        like=True,
        repost=True,
        bookmark=False,
        reply=True,
    )
    assert job.preset_replies == ("gm",)
    assert job.trace_id == "raid-1"


def test_detection_result_carries_job_for_detected_message() -> None:
    job = build_job()

    result = RaidDetectionResult.job_detected(job)

    assert result.kind == "job_detected"
    assert result.normalized_url == job.normalized_url
    assert result.job == job


def test_execution_result_exposes_structured_failure_kind() -> None:
    result = RaidExecutionResult(kind="page_ready_timeout", handed_off=False)

    assert result.kind == "page_ready_timeout"
    assert result.handed_off is False


def test_shared_models_reexport_browser_contracts() -> None:
    assert SharedRaidActionRequirements is RaidActionRequirements
    assert SharedRaidActionJob is RaidActionJob
    assert SharedRaidDetectionResult is RaidDetectionResult
    assert SharedRaidExecutionResult is RaidExecutionResult
