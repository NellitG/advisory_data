from django.db import models


class AdvisoryKnowledge(models.Model):
    value_chain = models.CharField(max_length=100)
    question = models.TextField()
    answer = models.TextField()

    def __str__(self):
        return f"{self.value_chain}: {self.question[:80]}"
