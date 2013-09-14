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
# the realm list on the front page gets populated
class LoadRealms(webapp2.RequestHandler):
    def get(self):
        # retrieve a list of realms from the blizzard API
        url = 'http://us.battle.net/api/wow/realm/status'
        response = urlfetch.fetch(url)
        jsondata = json.loads(response.content)

        for realm in jsondata['realms']:
            r = grouploader.Realm(realm=realm['name'], slug=realm['slug'],
                                namespace='Realms', id=realm['slug'])
            r.put()

app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/groups', GroupRedir),
    ('/loadrealms', LoadRealms),
    webapp2.Route('/edit/<:([^/]+)>/<:([^/]+)>', grouploader.Editor),
    webapp2.Route('/<:([^/]+)>/<:([^/]+)>', grouploader.Loader),
], debug=True)
