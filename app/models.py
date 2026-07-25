"""Pydantic request/response schemas for the HTTP API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class NoteIn(BaseModel):
    title: str = Field(..., min_length=1)
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    slug: str | None = None


class QueryIn(BaseModel):
    question: str = Field(..., min_length=1)
    k: int = Field(5, ge=1, le=20)


class GenerateIn(BaseModel):
    topic: str = Field(..., min_length=1)
    format_spec: str = Field(
        default=(
            "# {title}\n\n## Summary\n\n## Key Points\n- \n\n## Details\n\n"
            "## Related\n\n## References\n"
        ),
        description="The custom template / format the note should follow.",
    )
    k: int = Field(4, ge=0, le=20)
    save: bool = False


class RenderIn(BaseModel):
    """Convert previously-extracted JSON into a Markdown note — the second,
    explicit step after schema-based extraction (see POST /api/ingest and
    the Upload tab's "Convert to Markdown" button). `data` is a JSON object
    for object-rooted schemas, or a JSON array for array-rooted schemas
    (e.g. a list of extracted records)."""
    data: dict | list
    schema_name: str = ""
    source_filename: str = ""
    save: bool = False
