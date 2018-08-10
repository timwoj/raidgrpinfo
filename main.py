# -*- coding: utf-8 -*-
#!/usr/bin/env python

import webapp2
import jinja2,os
import grouploader,wowapi

from webapp2_extras import sessions

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'])

class MainHandler(webapp2.RequestHandler):
    def get(self):

        # load the list of realms from the datastore that was loaded by the
        # /loadrealms service
        q = wowapi.Realm.query(namespace='Realms')
        realms = q.fetch()

        # throw them at jinja to generate the actual html
        template_values = {
            'realms': realms,
        }
        template = JINJA_ENVIRONMENT.get_template('templates/frontpage.html')
        self.response.write(template.render(template_values))

# This class redirects using the input from the form on the main page to the
# right page for the group.
class GroupRedir(webapp2.RequestHandler):
    def post(self):
        # normalize the group name and realm name to make them simple strings
        # without spaces.  this makes it easier to work with them.
        realm = self.request.get('realm').strip()
        group = self.request.get('group').strip()
        nrealm = grouploader.Groupv2.normalize(realm)
        ngroup = grouploader.Groupv2.normalize(group)

        self.redirect('/%s/%s' % (nrealm, ngroup))

# Loads the list of realms into the datastore from the blizzard API so that
# the realm list on the front page gets populated.  Also loads the list of
# classes into a table on the DB so that we don't have to request it
class InitDB(webapp2.RequestHandler):
    def get(self):
        setup = wowapi.Setup()
        results = setup.initdb()
        self.response.write("Loaded %d realms into datastore<br/>" % results[0])
        self.response.write("Loaded %d classes into datastore<br/>" % results[1])

class MaintenanceHandler(webapp2.RequestHandler):
    def get(self):
        self.response.write("Raidgrpinfo is in maintenance mode and will return soon.")
    def get(self, nrealm, ngroup):
        self.response.write("Raidgrpinfo is in maintenance mode and will return soon.")

app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/groups', GroupRedir),
    ('/initdb', InitDB),
    ('/val', grouploader.Validator),
    ('/delete', grouploader.Deleter),
    ('/migratestatus', grouploader.StatusMigration),
    webapp2.Route('/edit/<:([^/]+)>/<:([^/]+)>', grouploader.Editor),
    webapp2.Route('/<:([^/]+)>/<:([^/]+)>', grouploader.GridLoader),
], debug=True)

# Maintenance mode stuff for when messing with the database
#app = webapp2.WSGIApplication([
#    ('/', MaintenanceHandler),
#    ('/initdb', InitDB),
#    ('/setapikey', SetAPIKey),
#    webapp2.Route('/edit/<:([^/]+)>/<:([^/]+)>', MaintenanceHandler),
#    webapp2.Route('/<:([^/]+)>/<:([^/]+)>', MaintenanceHandler),
#], debug=True)
