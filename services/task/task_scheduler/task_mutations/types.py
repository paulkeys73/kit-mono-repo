# task_scheduler/task_mutations/types.py
import graphene

class TaskType(graphene.ObjectType):
    id = graphene.ID()
    title = graphene.String()
    description = graphene.String()
    created_at = graphene.DateTime()
