from django.db import models


class AdvisoryKnowledge(models.Model):
    value_chain = models.CharField(max_length=100)
    question = models.TextField()
    answer = models.TextField()