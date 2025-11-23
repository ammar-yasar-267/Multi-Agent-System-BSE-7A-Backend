#!/usr/bin/env python3
"""
Test script for Intent Identification System
Run this to verify the intent identifier is working correctly
"""

import asyncio
import os
import sys
from pathlib import Path

REGISTRY_FILE = Path(__file__).parent.parent / "config" / "registry.json"

# Add parent directory to path to import supervisor modules
sys.path.insert(0, str(Path(__file__).parent))

from intent_identifier import IntentIdentifier

# Test queries for different agents
TEST_QUERIES = [
    # Quiz Agent
    ("Generate a quiz on Python programming with 10 questions", "adaptive_quiz_master_agent"),
    ("Create a test about data structures", "adaptive_quiz_master_agent"),
    ("I need practice questions on algorithms", "adaptive_quiz_master_agent"),
    
    # Assignment Coach
    ("Help me with my AI assignment", "assignment_coach_agent"),
    ("Break down this project task", "assignment_coach_agent"),
    ("I need guidance on my homework", "assignment_coach_agent"),
    
    # Plagiarism Prevention
    ("Check my essay for plagiarism", "plagiarism_prevention_agent"),
    ("Rephrase this paragraph to improve originality", "plagiarism_prevention_agent"),
    ("Is this text copied?", "plagiarism_prevention_agent"),
    
    # Research Scout
    ("Find research papers on machine learning", "research_scout_agent"),
    ("Search for articles about blockchain", "research_scout_agent"),
    ("Get me case studies on agile development", "research_scout_agent"),
    
    # Study Scheduler
    ("Create a study timetable for my exams", "study_scheduler_agent"),
    ("Help me organize my study time", "study_scheduler_agent"),
    ("Make a schedule for next week", "study_scheduler_agent"),
    
    # Citation Manager
    ("Generate an APA citation for this paper", "citation_manager_agent"),
    ("Format this reference in MLA style", "citation_manager_agent"),
    ("Create a bibliography", "citation_manager_agent"),
    
    # Concept Reinforcement
    ("I'm struggling with recursion, need more practice", "concept_reinforcement_agent"),
    ("Create flashcards for biology", "concept_reinforcement_agent"),
    ("Help me reinforce weak topics", "concept_reinforcement_agent"),
    
    # Presentation Feedback
    ("Analyze my presentation transcript", "presentation_feedback_agent"),
    ("Give feedback on my speech", "presentation_feedback_agent"),
    
    # Peer Collaboration
    ("Analyze our team discussion", "peer_collaboration_agent"),
    ("Who's not contributing in our group?", "peer_collaboration_agent"),
    
    # Question Anticipator
    ("Predict exam questions from the syllabus", "question_anticipator_agent"),
    ("What questions might appear in the test?", "question_anticipator_agent"),
    
    # Exam Readiness
    ("Assess my exam preparation", "exam_readiness_agent"),
    ("Create a mock exam", "exam_readiness_agent"),
    
    # General/Ambiguous (should go to gemini-wrapper or request clarification)
    ("What is quantum physics?", "gemini-wrapper"),
    ("Tell me about history", "gemini-wrapper"),
    ("I need help", None),  # Should be ambiguous
]

async def test_intent_identification():
    """Run tests on the intent identification system."""
    
    # Check if API key is set
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ ERROR: GEMINI_API_KEY environment variable not set!")
        print("Set it with: export GEMINI_API_KEY='your_key_here'")
        return False
    
    print("=" * 80)
    print("🧪 Testing Intent Identification System")
    print("=" * 80)
    print()
    
    identifier = IntentIdentifier()
    
    passed = 0
    failed = 0
    ambiguous = 0
    
    for i, (query, expected_agent) in enumerate(TEST_QUERIES, 1):
        print(f"\n📝 Test {i}/{len(TEST_QUERIES)}")
        print(f"Query: '{query}'")
        print(f"Expected Agent: {expected_agent or 'AMBIGUOUS'}")
        
        try:
            result = await identifier.identify_intent(query)
            
            identified_agent = result.get("agent_id")
            confidence = result.get("confidence", 0)
            is_ambiguous = result.get("is_ambiguous", False)
            reasoning = result.get("reasoning", "")
            
            print(f"Identified Agent: {identified_agent}")
            print(f"Confidence: {confidence:.2f}")
            print(f"Reasoning: {reasoning}")
            
            # Check if it's ambiguous when expected
            if expected_agent is None and is_ambiguous:
                print("✅ PASS - Correctly identified as ambiguous")
                ambiguous += 1
                passed += 1
                continue
            
            # Check if correct agent identified
            if identified_agent == expected_agent:
                if confidence >= 0.6:
                    print(f"✅ PASS - Correct agent with good confidence")
                    passed += 1
                else:
                    print(f"⚠️  PASS (low confidence) - Correct agent but confidence < 0.6")
                    passed += 1
            else:
                print(f"❌ FAIL - Expected {expected_agent}, got {identified_agent}")
                failed += 1
                
                # Show extracted params if any
                extracted = result.get("extracted_params", {})
                if extracted:
                    print(f"Extracted Params: {extracted}")
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
            failed += 1
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 Test Summary")
    print("=" * 80)
    print(f"Total Tests: {len(TEST_QUERIES)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"🤔 Ambiguous (expected): {ambiguous}")
    print(f"Success Rate: {(passed/len(TEST_QUERIES)*100):.1f}%")
    print()
    
    if failed == 0:
        print("🎉 All tests passed! Intent identification is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Review the agent descriptions and keywords.")
        return False

async def test_single_query(query: str):
    """Test a single query interactively."""
    
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ ERROR: GEMINI_API_KEY not set!")
        return
    
    print(f"\n🔍 Analyzing: '{query}'")
    print("-" * 80)
    
    identifier = IntentIdentifier()
    result = await identifier.identify_intent(query)
    
    print(f"Agent ID: {result.get('agent_id')}")
    print(f"Confidence: {result.get('confidence', 0):.2f}")
    print(f"Reasoning: {result.get('reasoning', '')}")
    print(f"Is Ambiguous: {result.get('is_ambiguous', False)}")
    
    extracted = result.get('extracted_params', {})
    if extracted:
        print(f"\nExtracted Parameters:")
        for key, value in extracted.items():
            print(f"  - {key}: {value}")
    
    alternatives = result.get('alternative_agents', [])
    if alternatives:
        print(f"\nAlternative Agents: {', '.join(alternatives)}")
    
    clarifying = result.get('clarifying_questions', [])
    if clarifying:
        print(f"\nClarifying Questions:")
        for q in clarifying:
            print(f"  - {q}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Intent Identification System")
    parser.add_argument(
        "--query", 
        type=str, 
        help="Test a single query instead of running all tests"
    )
    
    args = parser.parse_args()
    
    if args.query:
        asyncio.run(test_single_query(args.query))
    else:
        asyncio.run(test_intent_identification())