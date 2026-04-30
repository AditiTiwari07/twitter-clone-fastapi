from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import google.oauth2.id_token
from google.auth.transport import requests
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import starlette.status as status
from datetime import datetime, timedelta
from bson import ObjectId
from azure.storage.blob import BlobServiceClient, AccessPolicy, ContainerSasPermissions, PublicAccess

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

# Azurite connection string
azure_connection_str = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)

azure_service_client = BlobServiceClient.from_connection_string(azure_connection_str)
azure_container_name = "twitterclone"

try:
    azure_container_client = azure_service_client.get_container_client(azure_container_name)
    azure_container_client.create_container()
except Exception:
    print('container exists')
    azure_container_client = azure_service_client.get_container_client(azure_container_name)

try:
    azure_container_client.set_container_access_policy(
        signed_identifiers={},
        public_access=PublicAccess.CONTAINER
    )
    print("Container set to public read access.")
except Exception as e:
    print(f"Access policy error: {e}")

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

    if not user_info['username']:
        return RedirectResponse('/set-username', status_code=status.HTTP_302_FOUND)

    # Get all tweets sorted by newest first
    tweets = list(tweet_collection.find().sort('created_at', -1).limit(20))
    for tweet in tweets:
        tweet_user = user_collection.find_one({'username': tweet['username']})
        tweet['profile_pic'] = tweet_user.get('profile_pic', '') if tweet_user else ''
        if 'image' not in tweet:
            tweet['image'] = ''

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

    existing = user_collection.find_one({'username': username})
    if existing:
        return templates.TemplateResponse('username.html', {
            'request': request,
            'user_token': user_token,
            'error_message': 'Username already taken. Please choose another.'
        })

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

    if not content or len(content) > 280:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    image_url = ''
    file = form.get('tweet_image')
    if file and file.filename != '':
        if file.filename.endswith(('.jpg', '.jpeg', '.png')):
            contents = await file.read()
            blob_name = f'tweet_images/{user_info["username"]}/{file.filename}'
            azure_container_client.upload_blob(
                name=blob_name, data=contents, overwrite=True)
            blob_client = azure_container_client.get_blob_client(blob_name)
            image_url = blob_client.url

    tweet_dict = {
        'user_id': user_token['user_id'],
        'username': user_info['username'],
        'content': content,
        'created_at': datetime.now(),
        'image': image_url,
        'is_retweet': False,
        'retweeted_by': '',
        'original_username': ''
    }
    tweet_collection.insert_one(tweet_dict)
    return RedirectResponse('/', status_code=status.HTTP_302_FOUND)


# Search page
@app.get("/search", response_class=HTMLResponse)
async def searchPage(request: Request):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)
    user_info = getUser(user_token)
    return templates.TemplateResponse('search.html', {
        'request': request,
        'user_token': user_token,
        'user_info': user_info,
        'users': [],
        'tweets': [],
        'error_message': None
    })


# Search post
@app.post("/search", response_class=HTMLResponse)
async def searchPost(request: Request):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)
    user_info = getUser(user_token)
    form = await request.form()
    search_type = form['search_type']
    query = form['query']

    users = []
    tweets = []

    if search_type == 'username':
        users = list(user_collection.find(
            {'username': {'$regex': f'^{query}'}}
        ))
    elif search_type == 'tweet':
        tweets = list(tweet_collection.find(
            {'content': {'$regex': f'^{query}'}}
        ).sort('created_at', -1))

    return templates.TemplateResponse('search.html', {
        'request': request,
        'user_token': user_token,
        'user_info': user_info,
        'users': users,
        'tweets': tweets,
        'error_message': None
    })


# Profile page
@app.get("/profile/{username}", response_class=HTMLResponse)
async def profilePage(request: Request, username: str):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)
    user_info = getUser(user_token)

    profile_user = user_collection.find_one({'username': username})
    if not profile_user:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    profile_tweets = list(tweet_collection.find(
        {'username': username}
    ).sort('created_at', -1).limit(10))
    for tweet in profile_tweets:
        tweet_user = user_collection.find_one({'username': tweet['username']})
        tweet['profile_pic'] = tweet_user.get('profile_pic', '') if tweet_user else ''
        if 'image' not in tweet:
            tweet['image'] = ''

    is_following = username in user_info.get('following', [])

    return templates.TemplateResponse('profile.html', {
        'request': request,
        'user_token': user_token,
        'user_info': user_info,
        'profile_user': profile_user,
        'profile_tweets': profile_tweets,
        'is_following': is_following,
        'error_message': None
    })


# Follow user
@app.post("/follow/{username}", response_class=RedirectResponse)
async def followUser(request: Request, username: str):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)
    user_info = getUser(user_token)

    user_collection.update_one(
        {'user_id': user_token['user_id']},
        {'$addToSet': {'following': username}}
    )
    user_collection.update_one(
        {'username': username},
        {'$addToSet': {'followers': user_info['username']}}
    )
    return RedirectResponse(f'/profile/{username}',
        status_code=status.HTTP_302_FOUND)


# Unfollow user
@app.post("/unfollow/{username}", response_class=RedirectResponse)
async def unfollowUser(request: Request, username: str):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)
    user_info = getUser(user_token)

    user_collection.update_one(
        {'user_id': user_token['user_id']},
        {'$pull': {'following': username}}
    )
    user_collection.update_one(
        {'username': username},
        {'$pull': {'followers': user_info['username']}}
    )
    return RedirectResponse(f'/profile/{username}',
        status_code=status.HTTP_302_FOUND)


# Upload profile picture
@app.post("/upload-profile-pic", response_class=RedirectResponse)
async def uploadProfilePic(request: Request):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)
    user_info = getUser(user_token)

    form = await request.form()
    file = form['profile_pic']

    if file.filename == '':
        return RedirectResponse(f'/profile/{user_info["username"]}',
            status_code=status.HTTP_302_FOUND)

    if not file.filename.endswith(('.jpg', '.jpeg', '.png')):
        return RedirectResponse(f'/profile/{user_info["username"]}',
            status_code=status.HTTP_302_FOUND)

    contents = await file.read()
    blob_name = f'profile_pics/{user_info["username"]}/{file.filename}'
    azure_container_client.upload_blob(
        name=blob_name, data=contents, overwrite=True)
    blob_client = azure_container_client.get_blob_client(blob_name)
    pic_url = blob_client.url

    user_collection.update_one(
        {'user_id': user_token['user_id']},
        {'$set': {'profile_pic': pic_url}}
    )
    return RedirectResponse(f'/profile/{user_info["username"]}',
        status_code=status.HTTP_302_FOUND)


# Update bio
@app.post("/update-bio", response_class=RedirectResponse)
async def updateBio(request: Request):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)
    user_info = getUser(user_token)

    form = await request.form()
    bio = form['bio']

    if len(bio) > 280:
        return RedirectResponse(f'/profile/{user_info["username"]}',
            status_code=status.HTTP_302_FOUND)

    user_collection.update_one(
        {'user_id': user_token['user_id']},
        {'$set': {'bio': bio}}
    )
    return RedirectResponse(f'/profile/{user_info["username"]}',
        status_code=status.HTTP_302_FOUND)


# Delete tweet
@app.post("/delete-tweet", response_class=RedirectResponse)
async def deleteTweet(request: Request):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    form = await request.form()
    tweet_id = form['tweet_id']

    tweet_collection.delete_one({
        '_id': ObjectId(tweet_id),
        'user_id': user_token['user_id']
    })
    return RedirectResponse('/', status_code=status.HTTP_302_FOUND)


# Edit tweet page
@app.get("/edit-tweet/{tweet_id}", response_class=HTMLResponse)
async def editTweetPage(request: Request, tweet_id: str):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)
    user_info = getUser(user_token)

    tweet = tweet_collection.find_one({
        '_id': ObjectId(tweet_id),
        'user_id': user_token['user_id']
    })
    if not tweet:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse('edit_tweet.html', {
        'request': request,
        'user_token': user_token,
        'user_info': user_info,
        'tweet': tweet,
        'error_message': None
    })


# Edit tweet post
@app.post("/edit-tweet/{tweet_id}", response_class=RedirectResponse)
async def editTweet(request: Request, tweet_id: str):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)
    user_info = getUser(user_token)

    form = await request.form()
    content = form['content']

    if not content or len(content) > 280:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    # Preserve existing image if no new one uploaded
    existing_tweet = tweet_collection.find_one({'_id': ObjectId(tweet_id)})
    image_url = existing_tweet.get('image', '') if existing_tweet else ''

    file = form.get('tweet_image')
    if file and file.filename != '':
        if file.filename.endswith(('.jpg', '.jpeg', '.png')):
            contents = await file.read()
            blob_name = f'tweet_images/{tweet_id}/{file.filename}'
            azure_container_client.upload_blob(
                name=blob_name, data=contents, overwrite=True)
            blob_client = azure_container_client.get_blob_client(blob_name)
            image_url = blob_client.url

    update_data = {'content': content}
    if image_url:
        update_data['image'] = image_url

    tweet_collection.update_one(
        {'_id': ObjectId(tweet_id), 'user_id': user_token['user_id']},
        {'$set': update_data}
    )
    return RedirectResponse('/', status_code=status.HTTP_302_FOUND)


# Timeline
@app.get("/timeline", response_class=HTMLResponse)
async def timeline(request: Request):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)
    user_info = getUser(user_token)

    following = user_info.get('following', [])
    following.append(user_info['username'])

    tweets = list(tweet_collection.find(
        {'username': {'$in': following}}
    ).sort('created_at', -1).limit(20))
    for tweet in tweets:
        tweet_user = user_collection.find_one({'username': tweet['username']})
        tweet['profile_pic'] = tweet_user.get('profile_pic', '') if tweet_user else ''
        if 'image' not in tweet:
            tweet['image'] = ''

    return templates.TemplateResponse('timeline.html', {
        'request': request,
        'user_token': user_token,
        'user_info': user_info,
        'tweets': tweets,
        'error_message': None
    })


# Retweet
@app.post("/retweet/{tweet_id}", response_class=RedirectResponse)
async def retweet(request: Request, tweet_id: str):
    id_token = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)
    user_info = getUser(user_token)

    original_tweet = tweet_collection.find_one({'_id': ObjectId(tweet_id)})
    if not original_tweet:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    retweet_dict = {
        'user_id': user_token['user_id'],
        'username': user_info['username'],
        'content': original_tweet['content'],
        'created_at': datetime.now(),
        'image': original_tweet.get('image', ''),
        'is_retweet': True,
        'retweeted_by': user_info['username'],
        'original_username': original_tweet['username']
    }
    tweet_collection.insert_one(retweet_dict)
    return