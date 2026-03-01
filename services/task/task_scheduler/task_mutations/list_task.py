import graphene
from task_scheduler.models import Task

class TaskType(graphene.ObjectType):
    id = graphene.Int()
    name = graphene.String()
    description = graphene.String()

class ListTasks(graphene.Mutation):
    tasks = graphene.List(TaskType)

    def mutate(self, info):
        tasks = Task.objects.all()
        return ListTasks(tasks=tasks)
