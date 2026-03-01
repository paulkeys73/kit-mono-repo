import graphene
from task_scheduler.models import Task  # Assuming you have a Task model
from task_scheduler.task_mutations.types import TaskType

class CreateTask(graphene.Mutation):
    class Arguments:
        task_name = graphene.String()
        description = graphene.String()

    success = graphene.Boolean()
    task = graphene.Field(lambda: TaskType)  # Assuming TaskType is your GraphQL type for Task

    def mutate(self, info, task_name, description):
        task = Task.objects.create(name=task_name, description=description)
        return CreateTask(success=True, task=task)
