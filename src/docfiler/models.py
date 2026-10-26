"""Shared data types."""

from dataclasses import dataclass


@dataclass
class FilingSuggestion:
    """A suggested filename and destination for a document."""

    filename: str
    destination: str
    confidence: float
    reasoning: str

    def __str__(self) -> str:
        return f"{self.destination}/{self.filename}"
