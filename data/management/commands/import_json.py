import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from data.models import AdvisoryKnowledge


VALUE_CHAIN_KEYS = ("value_chain", "value chain", "valueChain", "value-chain")
QUESTION_KEYS = ("question", "Question")
ANSWER_KEYS = ("answer", "Answer")
LIST_KEYS = ("items", "data", "records", "results")


class Command(BaseCommand):
    help = "Import advisory knowledge rows from JSON files into db.sqlite3."

    def add_arguments(self, parser):
        parser.add_argument(
            "folder",
            type=str,
            help="Folder containing JSON files to import.",
        )
        parser.add_argument(
            "--recursive",
            action="store_true",
            help="Search for JSON files in subfolders too.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing AdvisoryKnowledge rows before importing.",
        )
        parser.add_argument(
            "--allow-duplicates",
            action="store_true",
            help="Insert duplicate rows instead of skipping exact matches.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate files and show what would be imported without writing to the database.",
        )

    def handle(self, *args, **options):
        folder = Path(options["folder"]).expanduser().resolve()
        if not folder.is_dir():
            raise CommandError(f"Folder not found: {folder}")

        pattern = "**/*.json" if options["recursive"] else "*.json"
        json_files = sorted(folder.glob(pattern))
        if not json_files:
            self.stdout.write(self.style.WARNING(f"No JSON files found in {folder}"))
            return

        rows = []
        errors = []
        skipped_blank_count = 0

        for json_file in json_files:
            try:
                records = self.load_records(json_file)
            except (json.JSONDecodeError, ValueError) as exc:
                errors.append(f"{json_file}: {exc}")
                continue

            for index, record in enumerate(records, start=1):
                try:
                    row = self.build_row(record, json_file)
                except ValueError as exc:
                    errors.append(f"{json_file} record {index}: {exc}")
                    continue

                if row is None:
                    skipped_blank_count += 1
                    continue

                rows.append(row)

        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(error))
            raise CommandError("Import stopped because one or more records are invalid.")

        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run complete: {len(rows)} rows are ready to import from {len(json_files)} file(s). "
                    f"Skipped {skipped_blank_count} blank row(s)."
                )
            )
            return

        with transaction.atomic():
            if options["clear"]:
                deleted_count, _ = AdvisoryKnowledge.objects.all().delete()
                self.stdout.write(f"Deleted {deleted_count} existing row(s).")

            if options["allow_duplicates"]:
                created_rows = rows
            else:
                created_rows = self.remove_existing_rows(rows)

            AdvisoryKnowledge.objects.bulk_create(created_rows, batch_size=500)

        skipped_count = len(rows) - len(created_rows)
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(created_rows)} row(s) from {len(json_files)} file(s). "
                f"Skipped {skipped_count} duplicate row(s) and {skipped_blank_count} blank row(s)."
            )
        )

    def load_records(self, json_file):
        with json_file.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            records = self.records_from_dict(payload, json_file)
        else:
            raise ValueError("top-level JSON must be an object or a list")

        if not all(isinstance(record, dict) for record in records):
            raise ValueError("each record must be a JSON object")

        return records

    def records_from_dict(self, payload, json_file):
        for key in LIST_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return value

        if not self.has_question_answer_fields(payload):
            return [
                {
                    "value_chain": json_file.stem,
                    "question": key,
                    "answer": value,
                }
                for key, value in payload.items()
            ]

        return [payload]

    def has_question_answer_fields(self, payload):
        return self.pick(payload, QUESTION_KEYS) is not None or self.pick(payload, ANSWER_KEYS) is not None

    def build_row(self, record, json_file):
        value_chain = self.pick(record, VALUE_CHAIN_KEYS) or json_file.stem
        question = self.pick(record, QUESTION_KEYS)
        answer = self.pick(record, ANSWER_KEYS)

        missing = [
            field
            for field, value in (
                ("question", question),
                ("answer", answer),
            )
            if not str(value or "").strip()
        ]
        if missing:
            return None

        return AdvisoryKnowledge(
            value_chain=str(value_chain).strip(),
            question=str(question).strip(),
            answer=str(answer).strip(),
        )

    def pick(self, record, keys):
        for key in keys:
            if key in record:
                return record[key]
        return None

    def remove_existing_rows(self, rows):
        existing = set(
            AdvisoryKnowledge.objects.filter(
                value_chain__in={row.value_chain for row in rows}
            ).values_list("value_chain", "question", "answer")
        )

        seen = set()
        created_rows = []
        for row in rows:
            key = (row.value_chain, row.question, row.answer)
            if key in existing or key in seen:
                continue
            seen.add(key)
            created_rows.append(row)

        return created_rows
