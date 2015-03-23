# -*- coding: utf-8 -*-

#!/usr/bin/env python

import webapp2,jinja2
import json,os,time
import wowapi
import logging

from datetime import datetime
from google.appengine.ext import ndb
from google.appengine.api.memcache import Client
from passlib.hash import sha256_crypt

# Minimum ilvls and colors for the ilvl grid
LFR_ILVL=655
MIN_NORMAL=665
MIN_HEROIC=680
COLOR_LFR="#FFB2B2"
COLOR_NORMAL="#FFFFB2"
COLOR_HEROIC="#B2FFB2"

# This is used to color the table cells on the grid display based on the ilvl
# of the item.  It gets put into the jinja environment as a filter.
def ilvlcolor(ilvl):
    if (ilvl == 0):
        return ''
    elif (ilvl < MIN_NORMAL):
        return 'background-color:'+COLOR_LFR
    elif ilvl >= MIN_NORMAL and ilvl < MIN_HEROIC:
        return 'background-color:'+COLOR_NORMAL
    elif ilvl >= MIN_HEROIC:
        return 'background-color:'+COLOR_HEROIC

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'])
JINJA_ENVIRONMENT.filters['ilvlcolor'] = ilvlcolor

class Group(ndb.Model):
    nrealm = ndb.StringProperty(indexed=True)
    ngroup = ndb.StringProperty(indexed=True)
    groupname = ndb.StringProperty()
    toons = ndb.StringProperty(repeated=True)
    password = ndb.StringProperty()

    @staticmethod
    def normalize(realm):
        return realm.lower().replace('\'','').replace(' ','-')

class Toonv2(ndb.Model):
    name = ndb.StringProperty(indexed=True)
    role = ndb.StringProperty()
    main = ndb.BooleanProperty()
    realm = ndb.StringProperty()

class Groupv2(ndb.Model):
    nrealm = ndb.StringProperty(indexed=True)
    ngroup = ndb.StringProperty(indexed=True)
    groupname = ndb.StringProperty()
    password = ndb.StringProperty()
    toons = ndb.StructuredProperty(Toonv2, repeated=True)
    lastvisited = ndb.DateTimeProperty()

    @staticmethod
    def normalize(realm):
        return realm.lower().replace('\'','').replace(' ','-')

class GroupStats:

    # the number of mains that should be used to calculate the group average
    # ilvl and equipped ilvls.  this may be different from the total number of
    # mains since there may be errors retrieving data from Battle.net.
    ilvlmains = 0
    totalilvl = 0
    totalilvleq = 0

    cloth = 0
    leather = 0
    mail = 0
    plate = 0

    # rogue/mage/druid/dk tokens
    vanq = 0
    # paladin/priest/warlock tokens
    conq = 0
    # warrior/hunter/shaman/monk tokens
    prot = 0

class Editor(webapp2.RequestHandler):
    def get(self, nrealm, ngroup):
        self.editGroup(nrealm, ngroup)

    def editGroup(self, nrealm, ngroup):

        # load the list of realms from the datastore that was loaded by the
        # /loadrealms service
        q = wowapi.Realm.query(namespace='Realms')
        realms = q.fetch()

        # try to load the group info from the database
        db_query = Groupv2.query(Groupv2.nrealm==nrealm, Groupv2.ngroup==ngroup)
        queryresults = db_query.fetch()

        results = None
        if (len(queryresults) != 0):
            results = queryresults[0]

        # Loop through the results from the data store and create a list
        # of toon names, the markers for subs, and the markers for
        # cross-realm.  If there weren't any results, blank lists will be
        # passed to the template.
        toons = list()
        if results != None:
           for toon in results.toons:
               t = dict()
               t['name'] = toon.name
               t['role'] = toon.role
               t['main'] = toon.main
               t['realm'] = str([x.realm for x in realms if x.slug==toon.realm][0])
               toons.append(t)

        # throw them at jinja to generate the actual html
        template_values = {
            'group' : ngroup,
            'nrealm' : nrealm,
            'realm' : str([x.realm for x in realms if x.slug==nrealm][0]),
            'toons' : toons,
            'realms' : realms,
        }
        template = JINJA_ENVIRONMENT.get_template('templates/editor.html')
        self.response.write(template.render(template_values))

class GridLoader(webapp2.RequestHandler):
    def get(self, nrealm, ngroup):
        # try to load the group info from the database
        db_query = Groupv2.query(Groupv2.nrealm==nrealm, Groupv2.ngroup==ngroup)
        results = db_query.fetch(1)

        # if the group doesn't exist, drop into the interface to make a new
        # group
        if (len(results) == 0):
            self.redirect('/edit/%s/%s' % (nrealm, ngroup))

        # if the group exists, load the group from the blizzard API and display
        # it.
        else:
            results[0].lastvisited = datetime.now()
            results[0].put()
            self.loadGroup(results[0])

    def post(self, nrealm, ngroup):

        # try to load the group info from the database.  this is only necessary
        # to get the password from the database to verify that it's correct.
        db_query = Groupv2.query(Groupv2.nrealm==nrealm, Groupv2.ngroup==ngroup)
        results = db_query.fetch(1)

        if ((len(results) != 0) and
            sha256_crypt.verify(self.request.get('pw'),
                                results[0].password) != True):
            self.response.write('<html><head><title>Password failure</title></head>\n')
            self.response.write('<body>\n')
            self.response.write('Password did not match for this group!<p/>')
            self.response.write('<a href="javascript:history.back()">Go Back</a>\n')
            self.response.write('</body></html>')
            self.response.status = 401
            return

        group = None
        if (len(results) != 0):
            group = results[0]
        else:
            group = Groupv2()

        group.nrealm = nrealm
        group.ngroup = ngroup
        group.groupname = self.request.get('group').strip()

        group.password = sha256_crypt.encrypt(self.request.get('pw'))

        # load the json data that includes the toon data
        jsontext = self.request.get('json').strip()
        logging.debug(jsontext.encode('ascii','ignore'))
        jsondata = json.loads(jsontext)
        logging.info('number of toons saved: %d' % len(jsondata['toons']))

        # clear the old toon information and recreate it from the data from
        # the form
        del group.toons[:]
        for j in jsondata['toons']:
            toon = Toonv2()
            toon.name = j['name']
            toon.role = j['role']
            if (j['group'] == 'main'):
                toon.main = True
            else:
                toon.main = False
            toon.realm = j['realm']
            group.toons.append(toon);

        group.toons = sorted(group.toons, key=lambda s: s.name.lower())
        group.lastvisited = datetime.now()
        group.put()

        # this is absolutely terrible, but sleep here for a second or two.
        # the reasoning is that the call from the editor page returns there
        # too quickly and will try to redirect to a page that doesn't exist
        # in the datastore yet.  that causes it to redirect back to the
        # editor page (see the get() function above).  sleeping here ensures
        # that the data was written before the redirection happens.
        results = list()
        while (len(results) == 0):
            time.sleep(0.5)
            db_query = Groupv2.query(Groupv2.nrealm==nrealm,
                                     Groupv2.ngroup==ngroup)
            results = db_query.fetch(1)

    def loadGroup(self, results):

        # Get the group data from the results
        toonlist = results.toons
        realm = results.nrealm

        # Query ndb for the full realm name based on the results
        rq = wowapi.Realm.query(wowapi.Realm.slug == realm, namespace='Realms')
        rqres = rq.fetch()
        frealm = rqres[0].realm

        q = wowapi.ClassEntry.query()
        res = q.fetch()

        classes = dict()
        for c in res:
            classes[c.classId] = c.name

        data = list()
        groupstats = GroupStats()

        # Use the API importer to load the data for the group into a list of
        # entries for each toon.  We'll loop through this data to build up
        # the page once all of the fetches are finished.
        importer = wowapi.Importer()
        importer.load(realm, frealm, toonlist, data, groupstats)

        # Catch the case where no mains were found in the data so we don't
        # divide by zero
        if groupstats.ilvlmains == 0:
            avgilvl = 0
            avgeqp = 0
        else:
            avgilvl = groupstats.totalilvl / groupstats.ilvlmains
            avgeqp = groupstats.totalilvleq / groupstats.ilvlmains

        # Build the page header with the group name, realm, and ilvl stats
        template_values = {
            'group' : results.groupname,
            'frealm' : frealm,
            'ngroup' : results.ngroup,
            'nrealm' : results.nrealm,
            'groupavgilvl' : avgilvl,
            'groupavgeqp' : avgeqp,
        }
        template = JINJA_ENVIRONMENT.get_template('templates/groupinfo-header.html')
        self.response.write(template.render(template_values))

        self.response.write('        <hr style="width:90%;clear: both"/><br/>\n')

        template_values = {
            'clothcount' : groupstats.cloth,
            'leathercount' : groupstats.leather,
            'mailcount' : groupstats.mail,
            'platecount' : groupstats.plate,
            'conqcount' : groupstats.conq,
            'protcount' : groupstats.prot,
            'vanqcount' : groupstats.vanq,
        }
        template = JINJA_ENVIRONMENT.get_template('templates/groupinfo-armortokens.html')
        self.response.write(template.render(template_values))

        self.response.write('        <hr style="width:90%;clear: both"/><br/>\n')

        template = JINJA_ENVIRONMENT.get_template('templates/groupinfo-gridheader.html')
        self.response.write(template.render(template_values))
        self.response.write('<tbody>\n')

        # Loop through the data twice here to display the separate sections,
        # but don't actually loop through all of the data.  The lambda filters
        # filter the character data down to just the parts that are needed
        # for each loop.
        for idx, char in enumerate(data):
            self.addCharacter(char, results, classes)

        self.response.write('</table><p/>\n')
        template = JINJA_ENVIRONMENT.get_template('templates/groupinfo-colorlegend.html')
        template_values = {
            'min_normal' : MIN_NORMAL,
            'min_heroic' : MIN_HEROIC,
            'color_lfr' : COLOR_LFR,
            'color_normal' : COLOR_NORMAL,
            'color_heroic' : COLOR_HEROIC,
        }
        self.response.write(template.render(template_values))

        self.response.write("        <div style='clear: both;font-size: 12px;text-align:center'>Site code by Tamen - Aerie Peak(US) &#149; <a href='http://github.com/timwoj/raidgrpinfo'>http://github.com/timwoj/raidgrpinfo<a/></div>")

        self.response.write('    </body>\n')
        self.response.write('</html>')

    # Generic method to add a character to the page response
    def addCharacter(self, char, results, classes):

        if 'status' in char and char['status'] == 'nok':
            template_values = {
                'name' : char['toon'],
                'status' : char['status'],
                'reason' : char['reason'],
            }
        elif 'items' in char:

            items = char['items']
            template_values = {
                'status' : 'ok',
                'name' : char['name'],
                'frealm' : char['toonfrealm'],   # full realm name
                'nrealm' : results.nrealm,  # realm for group
                'realm' : char['toonrealm'],  # realm for toon (might not be == to nrealm)
                'guild' : char['guild']['name'] if 'guild' in char else None,
                'class' : classes[char['class']],
                'main' : char['main'],
                'role' : char['role'],
                'avgilvl' : char['items']['averageItemLevel'],
                'avgilvle' : char['items']['averageItemLevelEquipped'],
                'lfrcount' : 0,
                'tiercount' : 0
            }

            # yes, feet are not part of normal tier gear, but they are part
            # of the lfr set.
            tierItems = ['head','shoulder','chest','hands','legs','feet']
            nonTierItems = ['neck','back','wrist','waist','feet','finger1','finger2','trinket1','trinket2','mainHand','offHand']

            # TODO: combine these two loops into one?
            for itype in tierItems:
                template_values[itype] = {}
                if itype in items:
                    template_values[itype]['id'] = items[itype]['id']
                    template_values[itype]['itemLevel'] = items[itype]['itemLevel']
                    template_values[itype]['bonusLists'] = items[itype]['bonusLists']
                    if 'tooltipParams' in items[itype]:
                        if 'set' in items[itype]['tooltipParams']:
                            if items[itype]['itemLevel'] == LFR_ILVL or items[itype]['itemLevel'] == LFR_ILVL+6:
                                template_values[itype]['set'] = 'lfr'
                                template_values['lfrcount'] += 1
                            elif items[itype]['itemLevel'] >= MIN_NORMAL:
                                template_values[itype]['set'] = 'norm'
                                template_values['tiercount'] += 1
                            else:
                                template_values[itype]['set'] = 'no'
                    else:
                        template_values[itype]['set'] = 'no'
                else:
                    template_values[itype]['itemLevel'] = 0
                    template_values[itype]['set'] = False

            for itype in nonTierItems:
                template_values[itype] = {}
                if itype in items:
                    template_values[itype]['id'] = items[itype]['id']
                    template_values[itype]['itemLevel'] = items[itype]['itemLevel']
                    template_values[itype]['bonusLists'] = items[itype]['bonusLists']
                else:
                    template_values[itype]['itemLevel'] = 0
                    template_values[itype]['set'] = 'no'

        else:

            template_values = {
                'name' : char['toon'],
                'status' : 'nok',
                'reason' : 'Unknown error retrieving data for %s.  Refresh to try again' % char['toon'],
            }

        template = JINJA_ENVIRONMENT.get_template('templates/groupinfo-gridtoon.html')
        self.response.write(template.render(template_values))

class PasswordValidator(webapp2.RequestHandler):
    def post(self):
        ngroup = self.request.get('group')
        nrealm = self.request.get('realm')
        pw = self.request.get('pw')

        db_query = Groupv2.query(Groupv2.nrealm==nrealm, Groupv2.ngroup==ngroup)
        results = db_query.fetch(1)
        if (len(results) != 0):
            if sha256_crypt.verify(pw, results[0].password) == False:
                self.response.status = 401
                self.response.write('Invalid')
            else:
                self.response.status = 200
                self.response.write('Valid')
        else:
            self.response.status = 200
            self.response.write('Valid')
