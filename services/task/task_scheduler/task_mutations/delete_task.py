import graphene
from task_scheduler.models import Task

class DeleteTask(graphene.Mutation):
    class Arguments:
        task_id = graphene.Int()

    success = graphene.Boolean()

    def mutate(self, info, task_id):
        try:
            task = Task.objects.get(id=task_id)
            task.delete()
            return DeleteTask(success=True)
        except Task.DoesNotExist:
            return DeleteTask(success=False)
