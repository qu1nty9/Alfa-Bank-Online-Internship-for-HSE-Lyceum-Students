"""Project configuration for the modular research pipeline."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class PipelineConfig(BaseModel):
    """Runtime settings shared by CLI, notebook, and future UI layers."""

    project_root: Path = Field(default_factory=lambda: Path.cwd())
    seed_sources_path: Path | None = None
    raw_dir: Path | None = None
    clean_dir: Path | None = None
    reports_dir: Path | None = None
    use_live_fetch: bool = False
    fetch_limit: int | None = None
    fetch_timeout_seconds: int = 25
    force_fetch: bool = False
    chunk_max_chars: int = 1200
    chunk_overlap_chars: int = 150
    chunk_min_chars: int = 160
    filter_min_chars: int = 200
    filter_min_domain_terms: int = 2
    top_k_per_query: int = 5
    max_evidence_items: int = 20
    min_clean_documents: int = 5
    min_evidence_items: int = 8
    min_evidence_sources: int = 4

    def resolved(self) -> "PipelineConfig":
        """Return a config with all path defaults resolved."""

        root = self.project_root
        return self.model_copy(
            update={
                "project_root": root,
                "seed_sources_path": self.seed_sources_path
                or root / "data" / "seed_sources" / "cltv_sources_template.csv",
                "raw_dir": self.raw_dir or root / "data" / "raw",
                "clean_dir": self.clean_dir or root / "data" / "clean",
                "reports_dir": self.reports_dir or root / "reports",
            }
        )


def default_pipeline_config(project_root: str | Path | None = None) -> PipelineConfig:
    """Create a resolved default config for the current repository."""

    root = Path(project_root) if project_root is not None else Path.cwd()
    return PipelineConfig(project_root=root).resolved()
