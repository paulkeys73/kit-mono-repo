import graphene
from task_scheduler.models import Task
from task_scheduler.task_mutations.types import TaskType


class EditTask(graphene.Mutation):
    class Arguments:
        task_id = graphene.Int()
        task_name = graphene.String()
        description = graphene.String()

    success = graphene.Boolean()
    task = graphene.Field(lambda: TaskType)  # Assuming TaskType is your GraphQL type for Task

    def mutate(self, info, task_id, task_name, description):
        try:
            task = Task.objects.get(id=task_id)
            task.name = task_name
            task.description = description
            task.save()
            return EditTask(success=True, task=task)
        except Task.DoesNotExist:
            return EditTask(success=False)
