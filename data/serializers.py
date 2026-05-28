from rest_framework import serializers


class RAGQuerySerializer(serializers.Serializer):
    question = serializers.CharField(max_length=1000)
    value_chain = serializers.CharField(max_length=100, required=False, allow_blank=True)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=10, default=5)
    include_sources = serializers.BooleanField(required=False, default=False)
