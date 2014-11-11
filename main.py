# -*- coding: utf-8 -*-
#!/usr/bin/env python

import cgi,json,pprint
import webapp2
import jinja2,os
import grouploader

from webapp2_extras import sessions
from google.appengine.api import urlfetch
from google.appengine.ext import ndb

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'])

class MainHandler(webapp2.RequestHandler):
    def get(self):
        
        # load the list of realms from the datastore that was loaded by the
        # /loadrealms service
        q = grouploader.Realm.query(namespace='Realms')
        realms = q.fetch()

        # throw them at jinja to generate the actual html
        template_values = {
            'realms': realms,
        }
        template = JINJA_ENVIRONMENT.get_template('frontpage.html')
        self.response.write(template.render(template_values))

# This class redirects using the input from the form to the right page
# for the group.
class GroupRedir(webapp2.RequestHandler):
    def post(self):
        # normalize the group name and realm name to make them simple strings
        # without spaces.  this makes it easier to work with them.
        realm = self.request.get('realm').strip()
        group = self.request.get('group').strip()
        nrealm = grouploader.Group.normalize(realm)
        ngroup = grouploader.Group.normalize(group)
        
        self.redirect('/%s/%s' % (nrealm, ngroup))

# Loads the list of realms into the datastore from the blizzard API so that
# the realm list on the front page gets populated.  Also loads the list of classes
# into a table on the DB so that we don't have to request it 
class InitDB(webapp2.RequestHandler):
    def get(self):

        q = grouploader.APIKey.query()
        apikey = q.fetch()[0]

        # retrieve a list of realms from the blizzard API
        url = 'https://us.api.battle.net/wow/realm/status?locale=en_US&apikey=%s' % apikey.key
        response = urlfetch.fetch(url)
        jsondata = json.loads(response.content)

        for realm in jsondata['realms']:
            r = grouploader.Realm(realm=realm['name'], slug=realm['slug'],
                                  namespace='Realms', id=realm['slug'])
            r.put()

        self.response.write("Loaded %d realms into datastore" % len(jsondata['realms']))

        url = 'https://us.api.battle.net/wow/data/character/classes?locale=en_US&apikey=%s' % apikey.key
        response = urlfetch.fetch(url)
        rawclasses = json.loads(response.content)
        cd = grouploader.ClassData()
        for c in rawclasses['classes']:
            ce = grouploader.ClassEntry(classId=c['id'], mask=c['mask'], powerType=c['powerType'], name=c['name'])
            cd.entries.append(ce)
        cd.put()

# The new Battle.net Mashery API requires an API key when using it.  This
# method stores an API in the datastore so it can used in later page requests.
class SetAPIKey(webapp2.RequestHandler):
    def get(self):

        argkey = self.request.get('key')
        if ((argkey == None) or (len(argkey) == 0)):
            self.response.write("Must pass API with 'key' argument in url")
        else:
            k = grouploader.APIKey(key=self.request.get('key'))
            k.put()
            self.response.write("API Key Stored.")

class UpdateToons(webapp2.RequestHandler):
    def get(self):

        groups = grouploader.Group.query()
        for group in groups:
            if group.ngroup == 'tlm20-wod' or group.ngroup == 'tlm20':
                for i in range(len(group.toons)):
                    if ',' not in group.toons[i]:
                        self.response.write("Updated toon %s in group %s\n" % (group.toons[i], group.ngroup))
                        group.toons[i] = group.toons[i]+',0,0'
            group.put()

app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/groups', GroupRedir),
    ('/initdb', InitDB),
    ('/setapikey', SetAPIKey),
    ('/updatetoons', UpdateToons),
    webapp2.Route('/edit/<:([^/]+)>/<:([^/]+)>', grouploader.Editor),
    webapp2.Route('/<:([^/]+)>/<:([^/]+)>', grouploader.Loader),
], debug=True)
