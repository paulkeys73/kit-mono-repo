from django.shortcuts import render, get_object_or_404, redirect
from .models import Task
from .forms import TaskForm

# View to list all tasks
def task_list(request):
    tasks = Task.objects.all()  # Retrieve all tasks from the database
    return render(request, 'task_scheduler/task-list.html', {'tasks': tasks})

# View to show details of a single task
def task_details(request, task_id):
    task = get_object_or_404(Task, id=task_id)  # Fetch task by ID or return 404 if not found
    return render(request, 'task_scheduler/task-details.html', {'task': task})

# View to create a new task
def create_task(request):
    if request.method == 'POST':
        form = TaskForm(request.POST)  # Populate form with POST data
        if form.is_valid():
            form.save()  # Save the new task
            return redirect('task-list')  # Redirect to the task list page
    else:
        form = TaskForm()  # Create an empty form for GET request
    return render(request, 'task_scheduler/create-task.html', {'form': form})

# View to edit an existing task
def edit_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task)  # Pre-populate form with task data
        if form.is_valid():
            form.save()  # Save the updated task
            return redirect('task-details', task_id=task.id)  # Redirect to task details page
    else:
        form = TaskForm(instance=task)  # Pre-fill form with task data
    return render(request, 'task_scheduler/task-edit.html', {'form': form, 'task': task})

# View to delete a task
def delete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.method == 'POST':
        task.delete()  # Delete the task
        return redirect('task-list')  # Redirect to the task list page
    return render(request, 'task_scheduler/task-delete.html', {'task': task})  # Render confirmation page
