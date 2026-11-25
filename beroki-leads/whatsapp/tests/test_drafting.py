import unittest

from whatsapp import drafting

from .fakes import contact, deal, good_draft
from .test_parsers import FakeResponse, FakeSession

SERVICES = ("Exterior renders", "Launch imagery")


def context():
    built, reason = drafting.context_for(contact("c1"), deal("d1", ["c1"]), SERVICES)
    assert reason is None
    return built


class ProjectNameTest(unittest.TestCase):
    def test_drops_the_da_suffix_and_the_postcode(self):
        self.assertEqual(drafting.project_name(deal("d1", ["c1"], name="Harbor Lane – DA A00123")), "Harbor Lane")
        self.assertEqual(drafting.project_name(deal("d1", ["c1"], name="12 Fictional St, West End QLD 4101 - DA 9")), "12 Fictional St, West End")
        self.assertEqual(drafting.project_name(deal("d1", ["c1"], name="100 Sample Ave, Miami FL 33131")), "100 Sample Ave, Miami")

    def test_refuses_a_name_that_still_holds_the_da_number(self):
        self.assertIsNone(drafting.project_name(deal("d1", ["c1"], da="A00123", name="A00123 Harbor Lane")))


class ProblemTest(unittest.TestCase):
    def test_accepts_a_good_draft(self):
        built = context()
        self.assertIsNone(drafting.problem(good_draft(built), built, "DA-0001"))

    def test_refuses_what_the_job_must_never_send(self):
        built = context()
        good = good_draft(built)
        cases = {
            "link": good.replace("examples?", "examples? www.example.com"),
            "email": good + " franco@example.com",
            "name": good.replace("Hi Alex", "Hi there"),
            "question": good.replace("examples?", "examples."),
            "number": good.replace("the renders", "the 75 renders"),
            "da": good.replace("the renders", "the renders for DA-0001"),
            "placeholder": good.replace("Alex", "{first_name}"),
            "long": good + " Thanks." * 60,
        }
        for label, message in cases.items():
            self.assertIsNotNone(drafting.problem(message, built, "DA-0001"), label)


class AgentClientTest(unittest.TestCase):
    def test_posts_the_context_with_the_secret(self):
        built = context()
        session = FakeSession([FakeResponse(body={"status": "draft", "message": good_draft(built)})])
        client = drafting.AgentClient("https://agent.invalid/", "secret", session)
        self.assertEqual(client.draft(built).status, "draft")
        self.assertEqual(session.headers["Authorization"], "Bearer secret")
        self.assertEqual(session.posts[0]["firstName"], "Alex")

    def test_review_and_errors(self):
        built = context()
        review = drafting.AgentClient("https://agent.invalid", "s", FakeSession([FakeResponse(body={"status": "review", "reason": "Planner"})]))
        self.assertEqual(review.draft(built).reason, "Planner")
        for response in (FakeResponse(status=503, body={}), FakeResponse(body={"status": "sent"}), FakeResponse(body=None, raw="oops")):
            client = drafting.AgentClient("https://agent.invalid", "s", FakeSession([response]))
            with self.assertRaises(drafting.DraftError):
                client.draft(built)


if __name__ == "__main__":
    unittest.main()
