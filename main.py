# -*- coding: utf-8 -*-
#!/usr/bin/env python

from flask import Flask, render_template, request
import grouploader
import wowapi
import logging
    
app = Flask(__name__)
logging.getLogger().setLevel(logging.DEBUG)

@app.route('/')
def root():

    # load the list of realms from the datastore that was loaded by the
    # /loadrealms service
    q = wowapi.Realm.query(namespace='Realms')
    realms = q.fetch()

    return render_template('frontpage.html', realms=realms)
    
# This class redirects using the input from the form on the main page to the
# right page for the group.
@app.route('/groups', methods=['POST'])
def groups():
    # normalize the group name and realm name to make them simple strings
    # without spaces.  this makes it easier to work with them.
    logger.warning('groups')
    realm = request.form['realm'].strip()
    group = request.form['group'].strip()
    nrealm = grouploader.Groupv2.normalize(realm)
    ngroup = grouploader.Groupv2.normalize(group)

    return redirect('/%s/%s' % (nrealm, ngroup), code=302)

# Loads the list of realms into the datastore from the blizzard API so that
# the realm list on the front page gets populated.  Also loads the list of
# classes into a table on the DB so that we don't have to request it
@app.route('/initdb')
def initdb():
    setup = wowapi.Setup()
    results = setup.initdb(app)
    return 'Loaded %d realms into datastore<br/>\nLoaded %d classes into datastore<br/>' % (results[0], results[1])
    
@app.route('/val')
def validator():
    return grouploader.validate_password()

@app.route('/<nrealm>/<ngroup>', methods=['GET', 'POST'])
def get_group():
    if request.method == 'GET':
        return grouploader.get_group(nrealm, ngroup)
    else:
        return grouploader.post_group(nrealm, ngroup)

@app.route('/edit/<nrealm>/<ngroup>')
def edit_group():
    return grouploader.edit_group(nrealm, ngroup)
