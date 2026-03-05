from pydantic import BaseModel
from typing import Literal
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AccessibilityIssue(BaseModel):
    severity: Severity
    message: str
    element: str
    line: int | None = None
    wcag_criterion: str | None = None  # ex: "WCAG 1.1.1"


class CodeSuggestion(BaseModel):
    line: int | None = None
    description: str
    original_code: str
    fixed_code: str


class AccessibilityReport(BaseModel):
    score: int  # 0–100
    issues: list[AccessibilityIssue]
    suggestions: list[CodeSuggestion]
    summary: str


class InvokeRequest(BaseModel):
    html_content: str
    pr_metadata: dict = {}


class InvokeResponse(BaseModel):
    score: int
    issues: list[AccessibilityIssue]
    suggestions: list[CodeSuggestion]
    summary: str
    filename: str | None = None
