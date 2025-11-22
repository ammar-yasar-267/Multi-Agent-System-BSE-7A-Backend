from pydantic import BaseModel
from typing import List, Optional, Dict

class YearRange(BaseModel):
    from_year: int
    to_year: int

class ResearchInput(BaseModel):
    topic: str
    keywords: List[str]
    year_range: YearRange
    max_results: int

class PaperItem(BaseModel):
    title: str
    authors: str
    year: int
    source: str
    link: str
    key_points: List[str]

class ResearchOutput(BaseModel):
    summary: str
    papers: List[PaperItem]
