from django.shortcuts import render

def home(request):
	return render(request, 'quan_ly_phieu_bau/home.html')

def permission_denied(request):
	return render(request, 'quan_ly_phieu_bau/common/permission_denied.html')

# All other views have been moved to their respective apps:
# - Account management views -> account app
# - Ballot management views -> ballot app  
# - Poll management views -> poll app
