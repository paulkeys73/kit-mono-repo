import graphene

class TaskMutation(graphene.Mutation):
    class Arguments:
        # Define arguments for your mutation
        task_name = graphene.String()

    # Define the mutation logic
    def mutate(self, info, task_name):
        # Add logic for your mutation here
        return TaskMutation(task_name=task_name)

    task_name = graphene.String()
