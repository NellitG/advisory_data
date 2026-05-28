import re

from django.core.management.base import BaseCommand
from data.models import AdvisoryKnowledge


QUESTION_STARTERS = (
    "how",
    "what",
    "where",
    "when",
    "why",
    "which",
    "who",
    "can",
    "should",
    "is",
    "are",
    "do",
    "does",
)


class Command(BaseCommand):
    help = "Convert AdvisoryKnowledge question topics into natural questions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show changes without writing them to the database.",
        )

    def handle(self, *args, **options):
        rows = AdvisoryKnowledge.objects.order_by("id")
        changes = []

        for row in rows:
            new_question = make_question(row.value_chain, row.question)
            if row.question != new_question:
                changes.append((row, new_question))

        for row, new_question in changes[:20]:
            self.stdout.write(f"{row.id}: {row.question} -> {new_question}")

        if len(changes) > 20:
            self.stdout.write(f"...and {len(changes) - 20} more change(s).")

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Dry run complete: {len(changes)} row(s) would change."))
            return

        for row, new_question in changes:
            row.question = new_question
            row.save(update_fields=["question"])

        self.stdout.write(self.style.SUCCESS(f"Updated {len(changes)} row(s)."))


def make_question(value_chain, topic):
    crop = clean_text(value_chain)
    topic = clean_text(topic)

    if not topic:
        return f"What advisory information is available for {crop}?"

    lower_topic = topic.lower()

    if "pest" in lower_topic and "disease" in lower_topic:
        return f"How do I manage pests and diseases in {crop}?"
    if "pest" in lower_topic:
        return f"How do I manage pests in {crop}?"
    if "disease" in lower_topic or "crop health" in lower_topic:
        return f"How do I manage diseases and crop health in {crop}?"
    if "weed" in lower_topic:
        return f"How do I manage weeds in {crop}?"
    if "water" in lower_topic or "irrigation" in lower_topic:
        return f"How do I manage water and irrigation for {crop}?"
    if "soil" in lower_topic or "fertil" in lower_topic or "manure" in lower_topic:
        return f"How do I manage soil fertility for {crop}?"
    if "land preparation" in lower_topic or lower_topic == "pre-planting":
        return f"How do I prepare land for {crop}?"
    if "site selection" in lower_topic or "where to plant" in lower_topic:
        return f"Where is the best place to plant {crop}?"
    if "planting material" in lower_topic or "planting materials" in lower_topic:
        return f"What planting materials should I use for {crop}?"
    if "planting" in lower_topic or "field establishment" in lower_topic:
        return f"How do I plant {crop}?"
    if "transplant" in lower_topic:
        return f"How do I transplant {crop}?"
    if "management/how to grow" in lower_topic or "how to grow" in lower_topic:
        return f"How do I grow and manage {crop}?"
    if "management" in lower_topic or "agronomic" in lower_topic:
        return f"How do I manage {crop}?"
    if "harvest" in lower_topic and "post" in lower_topic:
        return f"How do I harvest and handle {crop} after harvest?"
    if "harvest" in lower_topic:
        return f"How do I harvest {crop}?"
    if "storage" in lower_topic or "store" in lower_topic:
        return f"How do I store {crop}?"
    if "marketing" in lower_topic or "markets" in lower_topic:
        return f"How do I market {crop}?"
    if "value addition" in lower_topic or "utilization" in lower_topic or "processing" in lower_topic:
        return f"How can I add value to {crop}?"
    if "mechanization" in lower_topic:
        return f"What mechanization options are available for {crop}?"
    if "gross margin" in lower_topic or "cost" in lower_topic or "return" in lower_topic:
        return f"What are the costs and expected returns for {crop}?"
    if "variet" in lower_topic or "cultivar" in lower_topic or "seed" in lower_topic:
        return f"What varieties or seeds are recommended for {crop}?"
    if "maturity" in lower_topic:
        return f"How do I know when {crop} is mature?"
    if "further reading" in lower_topic or "contacts" in lower_topic:
        return f"Where can I find more information about {crop}?"
    if starts_like_question(lower_topic):
        return ensure_question_mark(topic)

    return f"What should I know about {topic.lower()} in {crop}?"


def clean_text(text):
    text = str(text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .:;")


def starts_like_question(lower_text):
    return lower_text.startswith(QUESTION_STARTERS)


def ensure_question_mark(text):
    return f"{text.rstrip(' ?')}?"
