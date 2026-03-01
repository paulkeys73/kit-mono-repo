import graphene
from task_scheduler.mutations import TaskMutation  # Import TaskMutation

class Query(graphene.ObjectType):
    dummy_field = graphene.String()

    def resolve_dummy_field(self, info):
        return "This is a dummy field"

class Mutation(TaskMutation, graphene.ObjectType):  # Use TaskMutation here
    pass

schema = graphene.Schema(query=Query, mutation=Mutation)
