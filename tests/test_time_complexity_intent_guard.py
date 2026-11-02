"""
Test to verify the intent engine guard for algorithmic 'time' queries.
Ensures queries like 'what is the time complexity of quicksort' do NOT match
system clock queries and instead fall through to informational/question processing.
"""
import unittest
from core.intent_engine import IntentEngine

class TestTimeComplexityIntentGuard(unittest.TestCase):
    def setUp(self):
        self.engine = IntentEngine()

    def test_clock_queries_still_match(self):
        clock_queries = [
            "what time is it",
            "what is the time",
            "tell me the time",
            "what's the time",
            "current time"
        ]
        for query in clock_queries:
            res = self.engine.parse(query)
            self.assertEqual(res.get("intent"), "time_query", f"Failed for query: {query}")

    def test_algorithmic_and_technical_time_queries_do_not_match_clock(self):
        tech_queries = [
            "what is the time complexity of quicksort",
            "what is the time complexity of binary search",
            "what is the time-complexity of merge sort",
            "what is the time series analysis method",
            "what is the time limit for this operation",
            "what is the time constant of an RC circuit",
            "what is the time travel paradox in physics"
        ]
        for query in tech_queries:
            res = self.engine.parse(query)
            self.assertNotEqual(
                res.get("intent"),
                "time_query",
                f"Query '{query}' was incorrectly matched to time_query instead of question/AI"
            )
            self.assertEqual(
                res.get("intent"),
                "question",
                f"Query '{query}' should be classified as question, got: {res.get('intent')}"
            )

if __name__ == "__main__":
    unittest.main()
