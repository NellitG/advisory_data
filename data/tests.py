from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from data.models import AdvisoryKnowledge
from data.rag import retrieve_context


class RAGTests(TestCase):
    def setUp(self):
        AdvisoryKnowledge.objects.create(
            value_chain="banana",
            question="Site selection",
            answer="Avoid water logging and choose well-drained soils.",
        )
        AdvisoryKnowledge.objects.create(
            value_chain="cabbage",
            question="Pest Management",
            answer="Monitor cabbages regularly for pest and disease occurrence.",
        )
        AdvisoryKnowledge.objects.create(
            value_chain="kales",
            question="Management/How To Grow",
            answer="Prepare seedbeds with banana leaves and manage pests by checking the field regularly.",
        )
        AdvisoryKnowledge.objects.create(
            value_chain="banana",
            question="Banana Pests",
            answer="Use clean planting material and control nematodes and banana weevils.",
        )

    def test_retrieve_context_finds_matching_rows(self):
        contexts = retrieve_context("How do I avoid water logging in banana?", limit=1)

        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0].value_chain, "banana")

    def test_retrieve_context_uses_crop_mentioned_in_question(self):
        contexts = retrieve_context("How do I manage banana pests?", limit=1)

        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0].value_chain, "banana")
        self.assertEqual(contexts[0].question, "Banana Pests")

    @override_settings(ROOT_URLCONF="config.urls")
    def test_rag_query_endpoint_returns_answer_and_sources(self):
        client = APIClient()

        response = client.post(
            reverse("rag-query"),
            {
                "question": "How should I choose a banana site?",
                "value_chain": "banana",
                "include_sources": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("answer", response.data)
        self.assertEqual(response.data["used_llm"], False)
        self.assertEqual(response.data["source"]["value_chain"], "banana")
        self.assertEqual(response.data["sources"][0]["value_chain"], "banana")
