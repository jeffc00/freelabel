from django.urls import path

from freelabel import views

urlpatterns = [
    path('', views.main, name='main'),

    path('register/', views.register, name='register'), 
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),

    path('initanns/', views.initanns, name='initanns'),
    path('refine/', views.refineCustom, name='refineCustom'),
    path('cmpGT/', views.cmpGT, name='cmpGT'),
    path('showFinalImg/', views.showFinalImg, name='showFinalImg'),

    path('play/', views.play, name='play'),


    path('video/', views.playVideo, name='playVideo'),

    path('playCustom/', views.playCustom, name='playCustom'),
    path('playCustom/loadcustom/', views.loadcustom, name='loadcustom'),
    path('playCustomScratch/', views.playCustomScratch, name='playCustom'),
    path('playCustomScratch/loadcustom/', views.loadcustom, name='loadcustom'),
    path('playCustomScratch/writeCustomLog/', views.writeCustomLog, name='writeCustomLog'),
    path('refineCustom/', views.refineCustom, name='refineCustom'),
    path('getfolder/', views.setcustomfolder, name='getfolder'),
    path('playCustom/writeCustomLog/', views.writeCustomLog, name='writeCustomLog'),
]
