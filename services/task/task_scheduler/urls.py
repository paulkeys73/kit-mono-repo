from django.urls import path
from . import views

urlpatterns = [
    path('', views.task_list, name='task-list'),  # Display all tasks at this path
    path('tasks/<int:task_id>/', views.task_details, name='task-details'),  # Task details route
    path('tasks/create/', views.create_task, name='task-create'),  # Create new task route
    path('tasks/<int:task_id>/edit/', views.edit_task, name='task-edit'),  # Edit existing task route
    path('tasks/<int:task_id>/delete/', views.delete_task, name='task-delete'),  # Delete task route
]
