import os
import random
import string
import datetime
from flask import Flask, render_template, request, flash, redirect, url_for
from flask import session as login_session, jsonify
from flask import send_from_directory, make_response
from flask.ext.seasurf import SeaSurf
from werkzeug import secure_filename
from werkzeug.contrib.atom import AtomFeed
from urlparse import urljoin

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Country, Base, University, User
import json
from oauth2client.client import flow_from_clientsecrets, FlowExchangeError
import httplib2
import requests

from functools import wraps


app = Flask(__name__)
csrf = SeaSurf(app)

# This is the path to the upload directory
app.config['UPLOAD_FOLDER'] = 'uploads/'
# These are the extension that we are accepting to be uploaded
app.config['ALLOWED_EXTENSIONS'] = set(['png', 'jpg', 'jpeg', 'gif'])

engine = create_engine('sqlite:///catalog.db')
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()

countries = session.query(Country).order_by(Country.name)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in login_session:
            return redirect(url_for('showLogin', next=request.url))
        return f(*args, **kwargs)
    return decorated_function
	
@app.route('/')
@app.route('/catalog/')

def home():
    """Route for home page / default view.

    Renders the template for the home page, displaying the Countries and
    the last 3 universites.

    """
    items = session.query(University).order_by(
        University.last_updated.desc()).limit(5)
    return render_template(
        "home.html",
        countries=countries,
        latest_universites=items)

def createUser(login_session):
    """Creates a new user based on details retrieved during login.
    """
    newUser = User(
        name=login_session['username'],
        email=login_session['email'],
        picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id

def getUserInfo(user_id):
    """Gets user based on user_id
    args:
        user_id: integer containing user_id
    """
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    """Gets user_id based on email address
    args:
        email: string containing email address
    """
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


@app.route('/login')
def showLogin():
    """Route for rendering the login screen and passing the state token
    """
    state = ''.join(
        random.choice(string.ascii_uppercase + string.digits)
        for x in range(32))
    login_session['state'] = state
    return render_template("login.html", STATE=state)

@csrf.exempt
@app.route('/connect/<string:provider>', methods=['POST'])
def connect(provider):
    """Route for authentication from login page
    csrf is exempt from this view because of the use of state tokens
    """
    state_token = request.args.get('state')
    if state_token != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    results = ""
    if provider == 'facebook':
        results = fbconnect()
    else:
        results = gconnect()
    # see if user exists, if it doesn't make a new one
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id
    flash("you are now logged in as %s" % login_session['username'])
    return results

def gconnect():
    """Connection and validation method for logging in using Google+
    """
    code = request.data
    auth_config = json.loads(open('client_secrets_google.json', 'r').read())[
        'web']

    try:
        oauth_flow = flow_from_clientsecrets(
            'client_secrets_google.json',
            scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(json.dumps('Failed to upgrade the \
            authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = credentials.access_token
    url = (auth_config['access_token_uri']
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response
    gplus_id = credentials.id_token['sub']
    # Verify user id's match
    if result['user_id'] != gplus_id:
        response = make_response(json.dumps("Token's user_id doesn't match \
            given user ID"), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # verify that the access token is valid for this app
    if result['issued_to'] != auth_config['client_id']:
        response = make_response(json.dumps("Token's client id doesn't \
            match apps"), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Check to see if user is already logged in
    stored_credentials = login_session.get('credentials')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_credentials is not None and gplus_id == stored_gplus_id:
        response = make_response(
            json.dumps('Current user is already connected'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # store the access token in the session for later use
    login_session['credentials'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # get user info
    userinfo_url = auth_config["userinfo_url"]
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()
    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']
    login_session['provider'] = "google"
    return "success"

def fbconnect():
    """Connection and validation method for logging in using Facebook
    """
    code = request.data
    auth_config = json.loads(open('client_secrets_facebook.json', 'r').read())[
        'web']
    app_id = auth_config['app_id']
    app_secret = auth_config['app_secret']
    url = auth_config['auth_url'] % (app_id, app_secret, code)
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]

    # Use token to get user info from API
    userinfo_url = auth_config['userinfo_url']
    # strip expire tag from access token
    token = result.split("&")[0]

    url = auth_config["scope_url"] % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    # print "url sent for API access:%s"% url
    # print "API JSON result: %s" % result
    data = json.loads(result)
    login_session['provider'] = 'facebook'
    login_session['username'] = data["name"]
    login_session['email'] = data["email"]
    login_session['facebook_id'] = data["id"]

    """ The token must be stored in the login_session in order to properly
    logout, let's strip out the information before the equals sign in our
    token
    """
    stored_token = token.split("=")[1]
    login_session['access_token'] = stored_token

    # Get user picture
    url = auth_config['picture_url'] % token  # noqa
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)
    login_session['picture'] = data["data"]["url"]

    return "success"

def gdisconnect():
    """Disconnect method for logging out of Google+
    """
    # Only disconnect a connected user.
    credentials = login_session['credentials']
    if credentials is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % credentials
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    if result['status'] != '200':
        # For whatever reason, the given token was invalid.
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


def fbdisconnect():
    """Disconnect method for logging out of Facebook
    """
    fbid = login_session['facebook_id']
    # The access token must me included to successfully logout
    access_token = login_session['access_token']
    url = 'https://graph.facebook.com/%s/permissions?access_token=%s' % (
        fbid,
        access_token)
    h = httplib2.Http()
    result = h.request(url, 'DELETE')[1]
    return "you have been logged out"


@app.route('/disconnect')
def disconnect():
    """Logout method for destroying session based on the provider used"""
    if 'provider' in login_session:
        if login_session['provider'] == 'google':
            gdisconnect()
            del login_session['gplus_id']
            del login_session['credentials']
        if login_session['provider'] == 'facebook':
            fbdisconnect()
            del login_session['facebook_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        del login_session['user_id']
        del login_session['provider']
        flash("You have successfully been logged out.")
    else:
        flash("You were not logged in")
    return redirect(url_for('home'))

@app.route('/catalog/country/<int:country_id>/')
@login_required
def catalogCountry(country_id):
    """Route for country page / country view.

    Renders the template for the country and lists the items within the
    country.

    Args:
        country_id: integer for the selected country
    """
    country = session.query(Country).filter_by(id=country_id).one()
    items = session.query(University).filter_by(country_id=country_id)
    return render_template(
        "country.html",
        country=country,
        universites=items,
        countries=countries)

@app.route('/catalog/item/<int:item_id>/')
def catalogItem(item_id):
    """Route for university page / university view.

    Renders the template for the items / universites. 
    Args:
        item_id: integer for the selected item
    """
    item = session.query(University).filter_by(id=item_id).one()
    images = getImages(item_id)
    country = session.query(Country).filter_by(id=item.country_id).one()
    return render_template(
        "item.html",
        item=item,
        countries=countries,
        country=country,
        images=images)

@app.route('/catalog/showImage/<int:item_id>/<string:filename>')
def showImage(item_id, filename):
    """Route to display the selected image and return to the browser

    Args:
        item_id: integer used for selecting the correct sub folder
        filename: string for the name of the image file
    """
    folderPath = app.config['UPLOAD_FOLDER'] + str(item_id)
    return send_from_directory(
        folderPath,
        filename)

@app.route('/catalog/showthumbnail/<int:item_id>')
def showThumbnail(item_id):
    """Route to display the thumbnail for the selected item

    Args:
        item_id: integer used for selecting the correct sub folder
    """
    folderPath = app.config['UPLOAD_FOLDER'] + str(item_id)
    filename = getThumbnail(item_id)
    return send_from_directory(
        folderPath,
        filename)

@app.route('/catalog/item/new/', methods=['GET', 'POST'])
@login_required
def addCatalogItem():
    """Route to either render the create a new item page or POST method
    for saving the new item
    """
    if request.method == 'POST':
        # POST method for saving new item
        # Converts date from EN-AU to Python date
        year_established = datetime.datetime.strptime(
            request.form['year_established'], "%d/%m/%Y").date()
        # details of new item
        newItem = University(
            university_name=request.form['university_name'],
            common_abbreviation=request.form['common_abbreviation'],
            year_established=year_established,
            description=request.form['description'],
            country_id=request.form['country'],
            user_id=login_session['user_id']
        )
        session.add(newItem)
        session.commit()

        # call to upload function
        uploadImages(newItem.id, request.files.getlist("files[]"))
        # store flash message and redirect to home page
        flash("University '%s' added" % newItem.university_name)
        return redirect(url_for('home'))
    else:
        # GET method which renders the new item page
        return render_template('newItem.html', countries=countries)

@app.route('/catalog/item/<int:item_id>/delete/', methods=['GET', 'POST'])
@login_required
def deleteCatalogItem(item_id):
    """Route to GET delete page or POST method

    Args:
        item_id: integer for id of item to delete
    """
    # get item here so that code to find item only needs to be called once
    item = session.query(University).filter_by(id=item_id).one()
    if (item.user_id != login_session["user_id"]):
        flash("You can only delete projects that you created")
        return redirect(url_for('home'))
    if request.method == 'POST':
        # POST method to delete item
        session.delete(item)
        session.commit()
        # call to function to remove the images from the item upload folder
        removeImages(item_id)
        # store flash message and redirect to home page
        flash("University '%s' has been deleted" % item.university_name)
        return redirect(url_for('home'))
    else:
        # GET method which renders the delete item confirmation page
        return render_template('deleteItem.html', item=item)

@app.route('/catalog/item/<int:item_id>/edit/', methods=['GET', 'POST'])
@login_required
def editCatalogItem(item_id):
    """Route to GET edit page or POST method

    Args:
        item_id: integer for id of item to update
    """

    item = session.query(University).filter_by(id=item_id).one()
    if item.user_id != login_session["user_id"]:
        flash("You can only edit University that you created")
        return redirect(url_for('home'))
    if request.method == 'POST':
        # POST method for saving changes to item
        item.university_name = request.form['university_name']
        item.common_abbreviation = request.form['common_abbreviation']
        item.year_established = datetime.datetime.strptime(
            request.form['year_established'], "%d/%m/%Y").date()
        item.description = request.form['description']
        item.country_id = request.form['country']
        session.add(item)
        session.commit()

        if (request.form['photooption'] == "replace"):
            """If the option to replace the photos is selected then the
            previous photos will be deleted and the new ones uploaded
            """
            # if the option to replace the images is selected then
            removeImages(item_id)
            uploadImages(item_id, request.files.getlist("files[]"))
        flash("University '%s' has been updated" % item.university_name)
        return redirect(url_for('home'))
    else:
        return render_template(
            'editItem.html',
            item=item,
            countries=countries)

def removeImages(item_id):
    """Deletes images from sub folder in the UPLOADS directory

    Args:
        item_id: integer for id of item to delete
    """
    imagePath = app.config['UPLOAD_FOLDER'] + str(item_id)
    if os.path.exists(imagePath):
        for file in os.listdir(imagePath):
            file_path = os.path.join(imagePath, file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception, e:
                print e


def uploadImages(item_id, files):
    """Uploads files to sub folder on server

    Args:
        item_id: id / name of subfolder for uploads
        files: list of files to upload to server
    """
    uploadPath = app.config['UPLOAD_FOLDER'] + str(item_id)
    # checks if folder exists if not create the sub folder
    if not os.path.exists(uploadPath):
        os.makedirs(uploadPath)
    """Loop through files and check if they are an allowed file type
    TODO: see if validation of file type can be done on client side rather
    than on the server side
    """
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(uploadPath, filename))


def allowed_file(filename):
    # For a given file, return whether it's an allowed type or not
    return '.' in filename and \
        filename.rsplit('.', 1)[1] in app.config['ALLOWED_EXTENSIONS']


def getImages(item_id):
    """Return a list of files in the folder linked to the item_id

    Args:
        item_id: id / name of subfolder for uploads
    """
    files = []
    folderPath = app.config['UPLOAD_FOLDER'] + str(item_id)
    if os.path.exists(folderPath):
        images = os.listdir(folderPath)
        for image in images:
            if "thumbnail" not in image and allowed_file(image):
                files.append(image)
    return files


def getThumbnail(item_id):
    """Returns the name of the file to be displayed as the thumbnail

    If a file does not contain the text 'thumbnail' the first file in the
    directory will be used

    Args:
        item_id: id / name of subfolder for uploads
    """
    files = []
    folderPath = app.config['UPLOAD_FOLDER'] + str(item_id)
    images = os.listdir(folderPath)
    filename = ""
    for image in images:
        if "thumbnail" in image and allowed_file(image):
            filename = image
    if filename == "":
        filename = getImages(item_id)[0]
    return filename


@app.route('/catalog/country/<int:country_id>/JSON')
def catalogCountryJSON(country_id):
    """Returns projects within country in a JSON format

    Args:
        country_id: id of the country
    """
    items = session.query(University).filter_by(country_id=country_id).all()
    return jsonify(University=[i.serialize for i in items])


@app.route('/catalog/JSON')
def catalogJSON():
    """Returns JSON view of all countries and their universities
    """
    countries = session.query(Country).all()
    serializedCountries = []
    for i in countries:
        new_coun = i.serialize
        items = session.query(University).filter_by(country_id=i.id).all()
        serializedItems = []
        for j in items:
            serializedItems.append(j.serialize)
        new_coun['items'] = serializedItems
        serializedCountries.append(new_coun)
    return jsonify(Countries=serializedCountries)


def make_external(url):
    """Returns external url for link back to item page

    Args:
        url: string containing url to Item page
    """
    return urljoin(request.url_root, url)


@app.route('/catalog/recent.atom')
def atom_feed():
    """Returns ATOM view of the 10 latest projects
    """
    feed = AtomFeed('Recent Projects',
                    feed_url=request.url, url=request.url_root)
    items = session.query(University).order_by(
        University.last_updated.desc()).limit(10)
    for item in items:
        feed.add(
            item.university_name,
            unicode(item.description),
            content_type='html',
            author=item.user.name,
            url=make_external(url_for('catalogItem', item_id=item.id)),
            updated=item.last_updated,
            published=item.last_updated)
    return feed.get_response()


if __name__ == '__main__':
    app.debug = True
    app.secret_key = 'super_secret_key'
    app.run(host='0.0.0.0', port=5000)
