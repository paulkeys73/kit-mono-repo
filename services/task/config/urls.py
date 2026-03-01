from django.contrib import admin
from django.urls import include, path
from graphene_django.views import GraphQLView

from task_scheduler.schema import schema

urlpatterns = [
    path('admin/', admin.site.urls),
    path('task/', include('task_scheduler.urls')),
    path('graphql/', GraphQLView.as_view(graphiql=True, schema=schema)),
]