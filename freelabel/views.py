import sys, os, glob
sys.path.append(os.getcwd()+"/freelabel")

from django.shortcuts import render

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect, HttpResponse
from django.contrib.auth.decorators import login_required

from django.shortcuts import render_to_response

# Import the Category model
from freelabel.models import Category, Page

from freelabel.forms import UserForm

import numpy as np
import json
import urllib.request as ur

from skimage.draw import line
from ourLib import startRGR, traceLine, cmpToGT, saveGTasImg, tracePolyline, readLocalImg, traceCircle, traceRect

from random import shuffle

import scipy.io as sio

import datetime, math

from threading import Thread

# for local folder usage (https://stackoverflow.com/questions/39801718/how-to-run-a-http-server-which-serves-a-specific-path)
from http.server import HTTPServer as BaseHTTPServer, SimpleHTTPRequestHandler
# import SimpleHTTPServer

class HTTPHandler(SimpleHTTPRequestHandler):
    # def do_POST(self):
    #     print("here")
    #     if self.path.startswith('/kill_server'):
    #         print("Server is going down, run it again manually!")
    #         def kill_me_please(server):
    #             server.shutdown()
    #             server.server_close()
    #         # httpd = HTTPServer('', ("", 8889))
    #         t=Thread(target=kill_me_please,args=(self.server,))
    #         t.start()                
    #         self.send_error(500)   
    #     print("move on")
    #     return  

    """This handler uses server.base_path instead of always using os.getcwd()"""
    def translate_path(self, path):
        path = SimpleHTTPRequestHandler.translate_path(self, path)
        relpath = os.path.relpath(path, os.getcwd())
        fullpath = os.path.join(self.server.base_path, relpath)
        return fullpath  

class HTTPServer(BaseHTTPServer):
    """The main server, you pass in base_path which is the path you want to serve requests from"""
    def __init__(self, base_path, server_address, RequestHandlerClass=HTTPHandler):
        self.base_path = base_path
        BaseHTTPServer.__init__(self, server_address, RequestHandlerClass)

# used to return numpy arrays via AJAX to JS side
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)

# defines which page (.html) is loaded first
def main(request):
    return render(request, 'freelabel/register.html')

# renders the main playing page
def play(request):    
    return render(request, 'freelabel/main.html')    

####
def playCustom(request):    
    return render(request, 'freelabel/customset.html')

def playCustomScratch(request):
    return render(request, 'freelabel/customsetScratch.html')

def threadfunction(web_dir):

    PORT = 8889
        # web_dir = '/home/philipe/Pictures/test/'
    httpd = HTTPServer(web_dir, ("", 0))   
    
    httpd.handle_request()

def setcustomfolder(httpd):
    # If the request is a HTTP POST, try to pull out the relevant information.
    # if request.method == 'POST':
        # web_dir = request.POST.get('folderpath')
    # web_dir = '/home/philipe/Pictures/test/'

    httpd.serve_forever()

    # print("###### DONE ###########")

    # return render(request, 'freelabel/register.html') 

def loadcustom(request):
    
    localFolder = request.POST.get('folderpath')
    setname = request.POST.get('datasetname')

    # # web_dir = '/home/philipe/Pictures/test/'
    # httpd = HTTPServer(localFolder, ("", PORT))
    # httpd.handle_request()

    httpd = HTTPServer(localFolder, ("", 0))
    sockinfo = httpd.socket.getsockname()
    PORT = sockinfo[1]

    t=Thread(target=setcustomfolder,args=[httpd])
    t.start()

    username = request.user.username

    # get list of files in folder of custom dataset
    imgList = []
    cnnList = []

    files_ = glob.glob(os.path.join(localFolder,"*.jpg"))
    files_.extend(glob.glob(os.path.join(localFolder,"*.png")))
    files_.extend(glob.glob(os.path.join(localFolder,"*.JPEG")))
    files_.extend(glob.glob(os.path.join(localFolder,"*.jpeg")))
    imgList = [os.path.basename(x) for x in files_]

    # in case of loading pre-segmentation maps
    for it,x in enumerate(files_):
        cnnList.append(imgList[it][0:-4] + ".png")

    # imgList = ['/' + s for s in imgList]
    print(imgList)
    catList = ['eraser']
    # load text file with list of categories in the dataset
    if os.path.exists(os.path.join(localFolder,'categories.txt')):
        f = open(os.path.join(localFolder,'categories.txt'), 'r')
        for elem in f.readlines():
            catList.append(elem)
        f.close()
    else:
        catList.append('background')
        catList.append('building')

    # check if there is already a sequence of images for this user.
    # If not, creates one
    filename = 'static/lists/imgs_' + setname + '_' + username + '.txt'
    if not os.path.exists(filename):
        shuffledIds = shuffleList(filename,len(imgList))
        # cnnList = cnnList[shuffledIds]

    idsList = np.loadtxt(filename, delimiter=',')    

    idsList = list(idsList)

    # get current total score and next image to be labeled
    filename = 'static/lists/info'+ setname +'_' + username + '.txt'
    if not os.path.exists(filename):
        nextId = 0
    else:          
        info = np.loadtxt(filename)   
        nextId = int(info)
    # to append bar if needed
    localFolder = os.path.join(localFolder,"")
    return HttpResponse(json.dumps({'PORT':PORT,'imgList': imgList,'cnnList': cnnList,'catList':catList,'idsList': idsList,'username': username,'nextId':nextId,'localFolder':localFolder}), content_type="application/json")

# redirecting for compatibility with older versions
def refine(request):
    refineCustom(request)

def refineCustom(request): 
    # get array of user traces from json 
    jsonAnns = json.loads(request.session['userAnns'])
    # convert it to numpy
    userAnns = np.array(jsonAnns["userAnns"])

    # get coordinates of trace to be drawn
    traces = request.POST.getlist('trace[]')   

    userAnns = drawTrace(userAnns,traces)

    # check if both classes have been annotated
    # list of annotated classes
    clsList = np.unique(userAnns)
    clsList = np.delete(clsList,0) # remove class 0
    numCls = clsList.size # number of classes

    if numCls > 1:
        username = request.user.username

        # flag indicating if annotation shall be merged with presegmentation
        mergePreSeg = True if request.POST.get('mergePreSeg') == 'true' else False

        # get URL of image
        url = request.POST.get('img')

        # get random ID that defines mask filename
        ID = request.POST.get('ID')
        # weight of traces, which defines the spacing between samples in RGR
        weight_ = int(request.POST.get('weight'))

        # theta_m: regulates weight of color-similarity vs spatial-proximity
        # divide by to adjust from [1,10] to [.1,1]
        m = float(request.POST.get('m'))/10

        # remove older files
        for filename in glob.glob("static/"+username+"/refined*"):
            os.remove(filename)

        # open image URL
        img = readLocalImg(url)
        # download image and convert to numpy array
        img = np.asarray(img, dtype="uint8")

        # call RGR and get mask as return
        im_color = startRGR(username,img,userAnns,ID,weight_,m,url,mergePreSeg)
        askForAnns = False
    else:
        askForAnns = True

    request.session['userAnns'] = json.dumps({'userAnns': userAnns}, cls=NumpyEncoder)
    # return render(request, 'freelabel/main.html')
    return HttpResponse(json.dumps({'askForAnns': askForAnns}), content_type="application/json")

def writeCustomLog(request):

    # get the username
    username = request.user.username

    jsonAnns = json.loads(request.session['userAnns'])
    anns = np.array(jsonAnns["userAnns"])

    # total score and next i in list of images to load
    next_i = int(request.POST.get('next_i'))  
    filename = 'static/lists/infoCustom_' + username + '.txt'
    np.savetxt(filename,[next_i], fmt='%d', delimiter=',')       

    #id of image
    img_file = request.POST.get('img_file')  

    # get newest ID of file once window reload  
    # file_ID = request.POST.get('fileID')    
    file_ID = username
    # save .mat with final mask and annotations, just in case we need it afterwards
    finalMask = np.load('static/'+username+'/lastmask.npy')
    
    setname = request.POST.get('datasetname')

    directory = 'static/log/masks/' + file_ID + '/' + setname  

    if not os.path.exists(directory):
        os.makedirs(directory)

    filename = directory + '/' + os.path.basename(img_file) + '.mat'
    sio.savemat(filename, mdict={'finalMask': finalMask, 'anns': anns})       

    # compute percentage of how many pixels were annotated by the user
    total_anns = np.count_nonzero(anns)
    total_anns = 100*(total_anns/anns.size)

    # filename = 'static/log/Results_' + file_ID + '.txt'
    filename = 'static/log/Log'+setname+'_' + username + '.txt'

    # if file exists, only append data
    if not os.path.exists(filename):
        a = open(filename, 'w+')
        a.close()

    #time spend
    time = request.POST.get('time')

    #number of traces
    trace_number = request.POST.get('trace_number')

    #length of all traces

    #number of clicks on "refine"
    refine_number = request.POST.get('refine_number')

    #accuracies obtained   
    accuracies = request.POST.getlist('accuracies[]')

    # string containing all info for this image: 
    str_ = str(os.path.basename(img_file)) + ';' +  str(time) + ';' + \
           str(trace_number) + ';' +  '%.3f'%(float(total_anns)) + ';' + \
           str(refine_number)\

    if accuracies is None:
        accuracies = 0

    for acc_ in accuracies:
        str_ = str_ + ',' + '%.3f'%(float(acc_))

    # get array of accuracies for each class + average. If empty (i.e. no refinement performed yet)
    str_ = str_ + '\n'

    a=open(filename, "a+")
    a.write(str_)
    a.close()

     # remove older files
    for filename in glob.glob("static/"+username+"/GTimage*"):
        os.remove(filename) 

    return render(request, 'freelabel/main.html')    

####
def playVideo(request):
    return render(request, 'freelabel/video.html')

def shuffleList(filename,lst_length):
    str_ = ''

    shuffled_ = np.random.permutation(lst_length)
    np.savetxt(filename, shuffled_, fmt='%d', delimiter=',')
    return shuffled_

# initialize array with user traces for this iamge
def initanns(request):

    username = request.user.username

    # delete pre-existent mask .npy file
    if os.path.exists('static/'+username+'/lastmask.npy',):
        os.remove('static/'+username+'/lastmask.npy',) 

    img_size = request.POST.getlist('img_size[]')    
    
    height = int(img_size[0])
    width = int(img_size[1])

    # create array with users annotations (same dimensions as image)
    userAnns = np.zeros((height,width),dtype=int)

    np.save('static/'+username+'/lastmask.npy', userAnns)

    # using sessions allow us to keep updating and accessing this same variable back and forth here in the views.py
    request.session['userAnns'] = json.dumps({'userAnns': userAnns}, cls=NumpyEncoder)  
    request.session.save()
    # get bounding boxes
    # download url as a local file
    #
    # return HttpResponse(json.dumps({'bbList': bbList}), content_type="application/json")
    return render(request, 'freelabel/main.html')


def cmpGT(request):
    username = request.user.username

    # get URL of ground truth file
    urlGT = request.POST.get('GT')
    # download this URL as local file GT.mat
    ur.urlretrieve(urlGT, "static/"+username+"/GT.mat")

    # call function that computes accuracies
    acc = cmpToGT(username)

    return HttpResponse(json.dumps({'acc': acc}, cls=NumpyEncoder), content_type="application/json")

def showFinalImg(request):
    username = request.user.username

    # get random ID that defines mask filename
    ID = int(request.POST.get('ID'))

    # remove older files
    for filename in glob.glob("static/"+username+"/GTimage*"):
        os.remove(filename) 

    # call asImg and get image  
    im_color = saveGTasImg(username,ID);

    return render(request, 'freelabel/main.html')

def drawTrace(userAnns,traces):

    img = np.uint8(userAnns)

    for itline in range(0,len(traces)):
        traceStr = traces[itline]
        trace = [x.strip() for x in traceStr.split(',')]

        # each trace "coordinate" contains: x,y,thickness,category,
        # so a line is defined by (trace[i],trace[i+1])--(trace[i+4],trace[i+5]), 
        # with thickness=trace[i+2] (or trace[i+6]) and category=trace[i+3](or trace[i+7])               
        pts = np.empty(shape=[0, 2])
        for i in range(0,len(trace)-6,5):
            
            # trace line between coordinates
            c0 = int(trace[i]) # i.e. x0
            r0 = int(trace[i+1]) # i.e. y0
            
            c1 = int(trace[i+5])
            r1 = int(trace[i+6])

            pts = np.append(pts,[[c0,r0]],axis=0)
            pts = np.append(pts,[[c1,r1]],axis=0)

            thick = int(trace[i+2])
            # workaround to the fact that JS variable can't handle negatives, but -1 indicates to CV to fill
            if thick > 8:
                thick = -1
            catId = int(trace[i+3])
            type_ = int(trace[i+4])

        if type_ == 0:
            userAnns = tracePolyline(img,pts,catId,thick)
        else:
            if type_ == 1:
                userAnns = traceCircle(img, pts, catId,thick)
            else:
                userAnns = traceRect(img,pts,catId,thick)

    return userAnns 

def register(request):

    # A boolean value for telling the template whether the registration was successful.
    # Set to False initially. Code changes value to True when registration succeeds.
    registered = False

    # If it's a HTTP POST, we're interested in processing form data.
    if request.method == 'POST':
        # Attempt to grab information from the raw form information.
        # Note that we make use of both UserForm and UserProfileForm.
        user_form = UserForm(data=request.POST)
        # profile_form = UserProfileForm(data=request.POST)

        # If the two forms are valid...
        if user_form.is_valid():
            # Save the user's form data to the database.
            user = user_form.save()

            # Now we hash the password with the set_password method.
            # Once hashed, we can update the user object.
            user.set_password(user.password)
            user.save()
    
            # Update our variable to tell the template registration was successful.
            registered = True

        # Invalid form or forms - mistakes or something else?
        # Print problems to the terminal.
        # They'll also be shown to the user.
        else:
            print (user_form.errors)

    # Not a HTTP POST, so we render our form using two ModelForm instances.
    # These forms will be blank, ready for user input.
    else:
        user_form = UserForm()
    
    # Render the template depending on the context.
    return render(request,
            'freelabel/register.html',
            {'user_form': user_form, 'registered': registered} )    

def user_login(request):

    # If the request is a HTTP POST, try to pull out the relevant information.
    if request.method == 'POST':
        # Gather the username and password provided by the user.
        # This information is obtained from the login form.
                # We use request.POST.get('<variable>') as opposed to request.POST['<variable>'],
                # because the request.POST.get('<variable>') returns None, if the value does not exist,
                # while the request.POST['<variable>'] will raise key error exception
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Use Django's machinery to attempt to see if the username/password
        # combination is valid - a User object is returned if it is.
        user = authenticate(username=username, password=password)

        # If we have a User object, the details are correct.
        # If None (Python's way of representing the absence of a value), no user
        # with matching credentials was found.
        if user:
            # Is the account active? It could have been disabled.
            if user.is_active:
                # If the account is valid and active, we can log the user in.
                # We'll send the user back to the homepage.
                login(request, user)

                # show log in time 
                username = request.user.username
                filename = 'static/log/Log_' + username + '.txt'

                # if file exists, only append data
                if not os.path.exists(filename):
                    a = open(filename, 'w+')
                    a.close()

                login_time = datetime.datetime.now()

                print(login_time)

                str_ = "#" + str(login_time) + '\n'

                a=open(filename, "a+")
                a.write(str_)
                a.close()

                directory = 'static/'+username

                if not os.path.exists(directory):
                    os.makedirs(directory)

                return HttpResponseRedirect('/freelabel/')
                # return render(request, 'freelabel/login.html', {})
            else:
                # An inactive account was used - no logging in!
                return HttpResponse("Your freelabel account is disabled.")
        else:
            # Bad login details were provided. So we can't log the user in.
            print ("Invalid login details: {0}, {1}".format(username, password))
            return HttpResponse("Invalid login details supplied.")

    # The request is not a HTTP POST, so display the login form.
    # This scenario would most likely be a HTTP GET.
    else:
        # No context variables to pass to the template system, hence the
        # blank dictionary object...
        return render(request, 'freelabel/login.html', {})

# Use the login_required() decorator to ensure only those logged in can access the view.
@login_required
def user_logout(request):
    # show log in time 
    username = request.user.username

    filename = 'static/log/Log_' + username + '.txt'

     # if file exists, only append data
    if not os.path.exists(filename):
        a = open(filename, 'w+')
        a.close()

    logout_time = datetime.datetime.now()


    print(logout_time)


    str_ = "!" + str(logout_time) + '\n'

    a=open(filename, "a+")
    a.write(str_)
    a.close()


    # Since we know the user is logged in, we can now just log them out.
    logout(request)

    # Take the user back to the homepage.
    return HttpResponseRedirect('/freelabel/register')           
