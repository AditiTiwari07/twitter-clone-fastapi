from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import google.oauth2.id_token
from google.auth.transport import requests
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import starlette.status as status
from datetime import datetime
from bson import ObjectId

# MongoDB connection
uri = "mongodb+srv://aditiuser:shubh%40123@cluster0.6opbt4j.mongodb.net/?appName=Cluster0"

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

# Define the app
app = FastAPI()

# Open the database and collections
db = client['A2-3195197']
user_collection = db['users']
tweet_collection = db['tweets']

# Firebase request adapter
firebase_request_adapter = requests.Request()

# Define static and templates directories
app.mount('/static', StaticFiles(directory='static'), name='static')
templates = Jinja2Templates(directory='templates')


# Function to validate firebase token
def validateFirebaseToken(id_token):
    if not id_token:
        return None
    user_token = None
    try:
        user_token = google.oauth2.id_token.verify_firebase_token(
            id_token, firebase_request_adapter)
    except ValueError as err:
        print(str(err))
    return user_token


# Function to get or create user
def getUser(user_token):
    user = user_collection.find_one({'user_id': user_token['user_id']})
    if not user:
        user_dict = {
            'user_id': user_token['user_id'],
            'username': None,
            'bio': '',
            'profile_pic': '',
            'followers': [],
            'following': []
        }
        user_collection.insert_one(user_dict)
        user = user_collection.find_one({'user_id': user_token['user_id']})
    return user


# Root route
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    id_token = request.cookies.get('token')
    error_message = 'No error here'
    user_token = None
    user_info = None
    tweets = []

    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return templates.TemplateResponse('main.html', {
            'request': request,
            'user_token': None,
            'error_message': None,
            'user_info': None,
            'tweets': []
        })

    user_info = getUser(user_token)

    # If user has no username yet, redirect to set username page
    if not user_info['username']:
        return RedirectResponse('/set-username', status_code=status.HTTP_302_FOUND)

    # Get all tweets sorted by newest first
    tweets = list(tweet_collection.find().sort('created_at', -1).limit(20))

    return templates.TemplateResponse('main.html', {
        'request': request,
        'user_token': user_token,
        'error_message': error_message,
        'user_info': user_info,
        'tweets': tweets
    })


# Set username page
@app.get("/set-username", response_class=HTMLResponse)
async def setUsernamePage(request: Request):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse('username.html', {
        'request': request,
        'user_token': user_token,
        'error_message': None
    })


# Set username post
@app.post("/set-username", response_class=RedirectResponse)
async def setUsername(request: Request):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    form = await request.form()
    username = form['username']

    # Check if username is unique
    existing = user_collection.find_one({'username': username})
    if existing:
        return templates.TemplateResponse('username.html', {
            'request': request,
            'user_token': user_token,
            'error_message': 'Username already taken. Please choose another.'
        })

    # Save username
    user_collection.update_one(
        {'user_id': user_token['user_id']},
        {'$set': {'username': username}}
    )
    return RedirectResponse('/', status_code=status.HTTP_302_FOUND)


# Post a tweet
@app.post("/post-tweet", response_class=RedirectResponse)
async def postTweet(request: Request):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    user_info = getUser(user_token)
    form = await request.form()
    content = form['content']

    # Validate content
    if not content or len(content) > 280:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    tweet_dict = {
        'user_id': user_token['user_id'],
        'username': user_info['username'],
        'content': content,
        'created_at': datetime.now(),
        'image': ''
    }
    tweet_collection.insert_one(tweet_dict)
    return RedirectResponse('/', status_code=status.HTTP_302_FOUND)