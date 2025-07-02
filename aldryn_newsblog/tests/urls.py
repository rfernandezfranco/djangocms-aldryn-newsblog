from django.contrib import admin
from django.urls import path
import cms.urls

urlpatterns = [
    path('admin/', admin.site.urls),
]
# Include the standard CMS urls so apphooked pages work
urlpatterns += cms.urls.urlpatterns
