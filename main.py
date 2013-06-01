# -*- coding: utf-8 -*-
#!/usr/bin/env python

import cgi,json,pprint
import webapp2
import grouploader
from webapp2_extras import sessions
from google.appengine.api import urlfetch
from google.appengine.ext import ndb

class MainHandler(webapp2.RequestHandler):
    def get(self):
        self.response.write('<html>\n')
        self.response.write('<head><title>Raid Group Info</title></head>\n')
        self.response.write('<body>\n')
        self.response.write('<form action="/groups" method="post">\n')
        self.response.write('<div>\n')
        self.response.write('Realm (US Only): <select name="realm" id="realm">\n')
        
        q = grouploader.Realm.query(namespace='Realms')
        realms = q.fetch()
        for r in realms:
            self.response.write('<option id="%s">%s\n' % (r.slug, r.realm))
        self.response.write('</select></div>\n')
        self.response.write('<div>Guild or Group name: <input type="text" name="group"></div>\n')
        self.response.write('<div><input type="submit" value="Load Group"></div>\n')
        self.response.write('</form>\n')
        self.response.write('</body>\n')
        self.response.write('</html>\n')

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
        
        # TODO: validate the realm against the armory
        
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
