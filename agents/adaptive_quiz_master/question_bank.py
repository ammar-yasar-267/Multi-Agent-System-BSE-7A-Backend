import json
import random
from typing import List, Dict, Optional

class QuestionBank:
    def __init__(self, file_path: str):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.questions = json.load(f)
        except FileNotFoundError:
            print(f"Warning: Question bank file not found at {file_path}. Using empty question bank.")
            self.questions = {}
        except json.JSONDecodeError as e:
            print(f"Warning: Error parsing question bank file: {e}. Using empty question bank.")
            self.questions = {}

    def get_questions(self, topic: str, question_types: List[str], bloom_level: str, difficulty: str, num_questions: int) -> List[Dict]:
        """Retrieve questions matching the criteria."""
        available_questions = self.questions.get(topic, [])
        
        filtered_questions = [
            q for q in available_questions
            if (q['type'] in question_types and
                q['bloom_taxonomy_level'] == bloom_level and
                q['difficulty'] == difficulty)
        ]
        
        # Shuffle and limit to num_questions
        random.shuffle(filtered_questions)
        return filtered_questions[:num_questions]

    def get_available_topics(self) -> List[str]:
        """Return list of available topics."""
        return list(self.questions.keys())