# -*- coding: utf-8 -*-
#!/usr/bin/env python

from flask import Flask, render_template, request, redirect
from google.appengine.api import wrap_wsgi_app

import grouploader
import wowapi

app = Flask(__name__)
app.wsgi_app = wrap_wsgi_app(app.wsgi_app)
app.debug = True

app.jinja_env.filters['ilvlcolor'] = grouploader.ilvlcolor
app.jinja_env.filters['normalize'] = grouploader.normalize
app.jinja_env.filters['build_wowhead_rel'] = grouploader.build_wowhead_rel
app.jinja_env.filters['build_jqx_widgets'] = grouploader.build_jqx_widgets

@app.route('/')
def root():

    # load the list of realms from the datastore that was loaded by the
    # /loadrealms service
    query = wowapi.Realm.query(namespace='Realms')
    realms = query.fetch()

    return render_template('frontpage.html', realms=realms)

# This class redirects using the input from the form on the main page to the
# right page for the group.
@app.route('/groups', methods=['POST'])
def groups():
    # normalize the group name and realm name to make them simple strings
    # without spaces.  this makes it easier to work with them.
    realm = request.form['realm'].strip()
    group = request.form['group'].strip()
    nrealm = grouploader.Groupv2.normalize(realm)
    ngroup = grouploader.Groupv2.normalize(group)

    return redirect('/%s/%s' % (nrealm, ngroup))

# Loads the list of realms into the datastore from the blizzard API so that
# the realm list on the front page gets populated.  Also loads the list of
# classes into a table on the DB so that we don't have to request it
@app.route('/initdb')
def initdb():
    setup = wowapi.Setup()
    results = setup.initdb(app)
    return 'Loaded %d realms into datastore<br/>\nLoaded %d classes into datastore<br/>' % (results[0], results[1])

@app.route('/val', methods=['POST'])
def validator():
    return grouploader.validate_password(request)

@app.route('/<nrealm>/<ngroup>', methods=['GET', 'POST'])
def group_handler(nrealm, ngroup):
    if request.method == 'GET':
        return grouploader.get_group(nrealm, ngroup)

    return grouploader.post_group(request, nrealm, ngroup)

@app.route('/edit/<nrealm>/<ngroup>')
def edit_handler(nrealm, ngroup):
    return grouploader.edit_group(nrealm, ngroup)

@app.after_request
def add_header(response):
    response.headers['Permissions-Policy'] = 'interest-cohort=()'
    return response
