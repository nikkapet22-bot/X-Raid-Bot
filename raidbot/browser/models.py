from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RaidActionRequirements:
    like: bool
    repost: bool
    bookmark: bool
    reply: bool

    def merged_with(self, defaults: "RaidActionRequirements") -> "RaidActionRequirements":
        return RaidActionRequirements(
            like=self.like or defaults.like,
            repost=self.repost or defaults.repost,
            bookmark=self.bookmark or defaults.bookmark,
            reply=self.reply or defaults.reply,
        )


@dataclass(frozen=True)
class RaidActionJob:
    normalized_url: str
    raw_url: str
    chat_id: int
    sender_id: int
    requirements: RaidActionRequirements
    preset_replies: tuple[str, ...]
    trace_id: str


@dataclass(frozen=True)
class RaidDetectionResult:
    kind: str
    normalized_url: str | None = None
    job: RaidActionJob | None = None
    reason: str | None = None

    @classmethod
    def job_detected(cls, job: RaidActionJob) -> "RaidDetectionResult":
        return cls(
            kind="job_detected",
            normalized_url=job.normalized_url,
            job=job,
            reason="job_detected",
        )


@dataclass(frozen=True)
class RaidExecutionResult:
    kind: str
    handed_off: bool
