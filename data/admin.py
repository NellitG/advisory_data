from django.contrib import admin

from data.models import AdvisoryKnowledge


@admin.register(AdvisoryKnowledge)
class AdvisoryKnowledgeAdmin(admin.ModelAdmin):
    list_display = ("value_chain", "question")
    search_fields = ("value_chain", "question", "answer")
