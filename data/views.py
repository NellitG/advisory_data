from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from data.rag import (
    answer_with_llm,
    answer_without_llm,
    fallback_source_rows,
    retrieve_context,
    short_source_payload,
    source_payload,
)
from data.serializers import RAGQuerySerializer


class RAGQueryView(APIView):
    def post(self, request):
        serializer = RAGQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        question = serializer.validated_data["question"]
        value_chain = serializer.validated_data.get("value_chain") or None
        limit = serializer.validated_data["limit"]
        include_sources = serializer.validated_data["include_sources"]

        contexts = retrieve_context(question, value_chain=value_chain, limit=limit)
        used_llm = False
        llm_error = None

        if contexts:
            try:
                answer = answer_with_llm(question, contexts)
                used_llm = answer is not None
            except RuntimeError as exc:
                answer = None
                llm_error = str(exc)
        else:
            answer = None

        if not answer:
            answer = answer_without_llm(question, contexts)

        source_rows = contexts[:1] if used_llm else fallback_source_rows(question, contexts)
        response = {
            "answer": answer,
            "used_llm": used_llm,
            "source": short_source_payload(source_rows[0]) if source_rows else None,
        }
        if include_sources:
            response["sources"] = [source_payload(row) for row in contexts]
        if llm_error:
            response["llm_error"] = llm_error

        return Response(response, status=status.HTTP_200_OK)
