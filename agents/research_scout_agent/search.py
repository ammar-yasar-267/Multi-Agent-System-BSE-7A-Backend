from .models import PaperItem, ResearchInput
import random

MOCK_SOURCES = ["IEEE", "Springer", "Elsevier", "ACM", "arXiv"]

def fake_paper(topic: str, keyword: str, year_range, idx: int) -> PaperItem:
    year = random.randint(year_range.from_year, year_range.to_year)
    return PaperItem(
        title=f"{topic} Study #{idx}",
        authors="John Doe, Jane Smith",
        year=year,
        source=random.choice(MOCK_SOURCES),
        link=f"https://example.com/paper-{idx}",
        key_points=[
            f"Key insight related to {topic}",
            f"Application of {keyword} in modern research",
            "Discussion of challenges and future directions"
        ]
    )

async def search_papers(data: ResearchInput):
    papers = []

    # Generate mock papers based on keywords
    for i, kw in enumerate(data.keywords[:data.max_results]):
        papers.append(fake_paper(data.topic, kw, data.year_range, i + 1))

    return papers
