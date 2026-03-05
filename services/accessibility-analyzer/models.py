from pydantic import BaseModel
from typing import Any, Optional


class SQSEvent(BaseModel):
    event_type: str  # "pull_request" ou "push"
    repo: str
    head_sha: str
    pr_number: Optional[int] = None  # presente apenas em pull_request
    head_ref: Optional[str] = None  # presente apenas em pull_request
    ref: Optional[str] = None  # presente apenas em push (ex: refs/heads/main)
    num_commits: Optional[int] = None  # presente apenas em push


class FileAnalysis(BaseModel):
    filename: str
    score: int
    issues: list[dict]
    suggestions: list[dict]
    summary: str


class AnalysisResult(BaseModel):
    repo: str
    pr_number: Optional[int] = None
    head_sha: str
    avg_score: float
    files_analyzed: int
    all_issues: list[dict]
    files: list[FileAnalysis]
    passed: bool
    bypass: dict | None = None
