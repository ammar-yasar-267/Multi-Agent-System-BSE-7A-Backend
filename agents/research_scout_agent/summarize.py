from .models import PaperItem
from typing import List

def generate_summary(papers: List[PaperItem], topic: str) -> str:
    if not papers:
        return f"No recent research found on '{topic}'."

    years = sorted([p.year for p in papers])
    sources = set([p.source for p in papers])

    return (
        f"Found {len(papers)} research papers on '{topic}' published between "
        f"{years[0]} and {years[-1]}. "
        f"Sources include: {', '.join(sources)}. "
        "The studies highlight key trends, modern applications, and ongoing challenges."
    )
