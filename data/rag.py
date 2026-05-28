import json
import os
import re
import urllib.error
import urllib.request

from data.models import AdvisoryKnowledge


TOKEN_RE = re.compile(r"[a-z0-9]+")
MAX_FALLBACK_ANSWER_LENGTH = 240
ACTION_WORDS = {
    "avoid",
    "check",
    "control",
    "destroy",
    "dip",
    "ensure",
    "harvest",
    "intercrop",
    "irrigate",
    "monitor",
    "mulch",
    "practice",
    "remove",
    "removed",
    "rotate",
    "select",
    "spray",
    "store",
    "use",
    "water",
}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "do",
    "for",
    "how",
    "i",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "the",
    "to",
    "what",
    "when",
    "where",
    "with",
}


def normalize(text):
    """Return lowercase words joined by spaces for simple text comparison."""
    return " ".join(TOKEN_RE.findall(str(text).lower()))


def singularize(token):
    """Handle simple plural words so pest and pests can match."""
    if len(token) > 3 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def get_keywords(text):
    words = set(TOKEN_RE.findall(str(text).lower()))
    tokens = words - STOPWORDS
    return tokens | {singularize(token) for token in tokens}


def find_crop_in_question(question):
    """Look for a value_chain name in the question."""
    normalized_question = f" {normalize(question)} "
    matches = []

    value_chains = AdvisoryKnowledge.objects.values_list("value_chain", flat=True).distinct()
    for crop_name in value_chains:
        normalized_crop_name = normalize(crop_name)
        if f" {normalized_crop_name} " in normalized_question:
            matches.append(crop_name)

    if not matches:
        return None

    return max(matches, key=lambda crop_name: len(normalize(crop_name)))


def retrieve_context(question, value_chain=None, limit=5):
    question_keywords = get_keywords(question)
    if not question_keywords:
        return []

    crop_name = value_chain or find_crop_in_question(question)
    queryset = AdvisoryKnowledge.objects.all()
    if crop_name:
        queryset = queryset.filter(value_chain__iexact=crop_name)

    scored_rows = []
    for row in queryset.iterator():
        score = score_row(question_keywords, row, crop_name)
        if score == 0:
            continue

        scored_rows.append((score, row))

    scored_rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored_rows[:limit]]


def score_row(question_keywords, row, crop_name=None):
    """Give higher scores to rows where the crop and topic match the question."""
    crop_matches = len(question_keywords & get_keywords(row.value_chain))
    topic_matches = len(question_keywords & get_keywords(row.question))
    answer_matches = len(question_keywords & get_keywords(row.answer))

    score = (crop_matches * 8) + (topic_matches * 5) + answer_matches
    if crop_name and normalize(crop_name) == normalize(row.value_chain):
        score += 10

    return score


def build_messages(question, contexts):
    context_text = "\n\n".join(
        (
            f"Source {index}\n"
            f"Value chain: {row.value_chain}\n"
            f"Topic: {row.question}\n"
            f"Information: {row.answer}"
        )
        for index, row in enumerate(contexts, start=1)
    )

    return [
        {
            "role": "system",
            "content": (
                "You are a friendly agricultural advisory assistant. "
                "Answer using only the supplied context. "
                "If the context does not contain enough information, say so and suggest what to ask next. "
                "Give a direct solution first, then mention the source topic you used. "
                "Keep the answer practical, clear, and warm."
            ),
        },
        {
            "role": "user",
            "content": f"Context:\n{context_text}\n\nQuestion: {question}",
        },
    ]


def answer_with_llm(question, contexts):
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        return None

    api_url = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": build_messages(question, contexts),
        "temperature": 0.3,
    }

    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("LLM response did not include a chat message.") from exc


def answer_without_llm(question, contexts):
    if not contexts:
        return (
            "I could not find matching advisory information for that question yet. "
            "Try mentioning the crop or topic, for example planting, pests, diseases, harvesting, or storage."
        )

    return make_friendly_fallback_answer(question, contexts)


def make_friendly_fallback_answer(question, contexts):
    crop_name = contexts[0].value_chain
    solution_items = get_solution_items(question, contexts, crop_name)
    solution_points = [item["text"] for item in solution_items]
    source_topics = unique_source_topics(solution_items, contexts)

    return (
        f"Solution for {crop_name}: {format_solution_points(solution_points)} "
        f"Source: {source_topics}."
    )


def get_solution_items(question, contexts, crop_name, max_points=3):
    relevant_keywords = get_relevant_solution_keywords(question, crop_name)
    action_items = []
    fallback_items = []

    for row in contexts:
        for sentence in split_sentences(row.answer):
            cleaned_sentence = clean_sentence(sentence)
            if not cleaned_sentence:
                continue

            item = {"text": cleaned_sentence, "row": row}
            fallback_items.append(item)
            if has_action_word(cleaned_sentence) and matches_question_topic(cleaned_sentence, relevant_keywords):
                item = {"text": clean_action_sentence(cleaned_sentence), "row": row}
                action_items.append(item)

            if len(action_items) >= max_points:
                return action_items[:max_points]

    if action_items:
        return action_items[:max_points]

    return fallback_items[:max_points]


def format_solution_points(points):
    if not points:
        return "I found related information, but not enough clear steps to give a strong solution."

    return " ".join(f"{index}. {point}" for index, point in enumerate(points, start=1))


def split_sentences(text):
    text = re.sub(r"\s+", " ", str(text)).strip()
    return re.split(r"(?<=[.!?])\s+", text)


def clean_sentence(sentence):
    sentence = sentence.strip(" .")
    if not sentence:
        return ""
    return f"{sentence}."


def has_action_word(sentence):
    words = set(normalize(sentence).split())
    return bool(words & ACTION_WORDS)


def clean_action_sentence(sentence):
    words = sentence.split()
    normalized_words = [normalize(word) for word in words]

    for index, word in enumerate(normalized_words):
        if word in ACTION_WORDS:
            cleaned = " ".join(words[index:])
            return cleaned[0].upper() + cleaned[1:]

    return sentence


def matches_question_topic(sentence, relevant_keywords):
    if not relevant_keywords:
        return True

    sentence_keywords = get_keywords(sentence)
    return bool(sentence_keywords & relevant_keywords)


def get_relevant_solution_keywords(question, crop_name):
    keywords = get_keywords(question) - get_keywords(crop_name)

    if "pest" in keywords:
        keywords.update({"control", "damage", "disease", "nematode", "weevil"})

    return keywords


def unique_source_topics(solution_items, contexts):
    if solution_items:
        topics = [item["row"].question for item in solution_items]
    else:
        topics = [row.question for row in contexts[:1]]

    unique_topics = []
    for topic in topics:
        if topic not in unique_topics:
            unique_topics.append(topic)

    return ", ".join(unique_topics[:2])


def shorten_text(text, max_length=MAX_FALLBACK_ANSWER_LENGTH):
    if len(text) <= max_length:
        return text

    return f"{text[:max_length].rsplit(' ', 1)[0]}..."


def first_sentences(text, sentence_count=2):
    sentences = split_sentences(text)
    useful_sentences = [sentence for sentence in sentences if sentence]
    return " ".join(useful_sentences[:sentence_count])


def source_payload(row):
    return {
        "id": row.id,
        "value_chain": row.value_chain,
        "question": row.question,
        "answer": row.answer,
    }


def short_source_payload(row):
    return {
        "id": row.id,
        "value_chain": row.value_chain,
        "topic": row.question,
    }


def fallback_source_rows(question, contexts):
    if not contexts:
        return []

    crop_name = contexts[0].value_chain
    solution_items = get_solution_items(question, contexts, crop_name)
    rows = []

    for item in solution_items:
        row = item["row"]
        if row not in rows:
            rows.append(row)

    return rows or contexts[:1]
