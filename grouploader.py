# -*- coding: utf-8 -*-

#!/usr/bin/env python

import webapp2,jinja2
import json,math,sys,os,time
import pprint
from datetime import datetime
from google.appengine.ext import ndb
from google.appengine.api.memcache import Client
from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_errors
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

class Realm(ndb.Model):
    realm = ndb.StringProperty(indexed=True,required=True)
    slug = ndb.StringProperty(indexed=True,required=True)

class APIKey(ndb.Model):
    key = ndb.StringProperty(indexed=True,required=True)

class ClassEntry(ndb.Model):
    classId = ndb.IntegerProperty()
    mask = ndb.IntegerProperty()
    powerType = ndb.StringProperty()
    name = ndb.StringProperty()

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

class APIImporter:

    def load(self, realm, frealm, toonlist, data, groupstats):
        q = APIKey.query()
        apikey = q.fetch()[0]

        q = ClassEntry.query()
        res = q.fetch()

        classes = dict()
        for c in res:
            classes[c.classId] = c.name

        # Request all of the toon data from the blizzard API and determine the
        # group's ilvls, armor type counts and token type counts.  subs are not
        # included in the counts, since they're not really part of the main
        # group.
        for toon in toonlist:
            toonname = toon.name
            toonrealm = toon.realm
            toonmain = toon.main
            if (toonrealm == realm):
                toonfrealm = frealm
            else:
                rq2 = Realm.query(
                    Realm.slug == toonrealm, namespace='Realms')
                rq2res = rq2.fetch()
                toonfrealm = rq2res[0].realm
            
            # TODO: this object can probably be a class instead of another dict
            newdata = dict()
            data.append(newdata)

            # a realm is received in the json data from the API, but we need to
            # pass the normalized value to the next stages.  ignore this field
            # from the data.
            newdata['toonrealm'] = toonrealm
            newdata['toonfrealm'] = toonfrealm
            newdata['main'] = toonmain

            url = 'https://us.api.battle.net/wow/character/%s/%s?fields=items,guild&locale=en_US&apikey=%s' % (toonrealm, toonname, apikey.key)
            # create the rpc object for the fetch method.  the deadline
            # defaults to 5 seconds, but that seems to be too short for the
            # Blizzard API site sometimes.  setting it to 10 helps a little
            # but it makes page loads a little slower.
            rpc = urlfetch.create_rpc(10)
            rpc.callback = self.create_callback(rpc, toonname, newdata, groupstats, classes)
            urlfetch.make_fetch_call(rpc, url)
            newdata['rpc'] = rpc

            # The Blizzard API has a limit of 10 calls per second.  Sleep here
            # for a very brief time to avoid hitting that limit.
            time.sleep(0.1)

        # Now that all of the RPC calls have been created, loop through the data
        # dictionary one more time and wait for each fetch to be completed. Once
        # all of the waits finish, then we have all of the data from the
        # Blizzard API and can loop through all of it and build the page.
        start = time.time()
        for d in data:
            d['rpc'].wait()
        end = time.time()
        print "Time spent retrieving data: %f seconds" % (end-start)

    # Callback that handles the result of the call to the Blizzard API.  This will fill in
    # the toondata dict for the requested toon with either data from Battle.net or with an
    # error message to display on the page.
    def handle_result(self, rpc, name, toondata, groupstats, classes):

        try:
            response = rpc.get_result()
        except urlfetch_errors.DeadlineExceededError:
            print('urlfetch threw DeadlineExceededError on toon %s' % name.encode('ascii','ignore'))
            toondata['toon'] = name
            toondata['status'] = 'nok'
            toondata['reason'] = 'Timeout retrieving data from Battle.net for %s.  Refresh page to try again.' % name
            return
        except urlfetch_errors.DownloadError:
            print('urlfetch threw DownloadError on toon %s' % name.encode('ascii','ignore'))
            toondata['toon'] = name
            toondata['status'] = 'nok'
            toondata['reason'] = 'Network error retrieving data from Battle.net for toon %s.  Refresh page to try again.' % name
            return
        except:
            print('urlfetch threw unknown exception on toon %s' % name.encode('ascii','ignore'))
            toondata['toon'] = name
            toondata['status'] = 'nok'
            toondata['reason'] = 'Unknown error retrieving data from Battle.net for toon %s.  Refresh page to try again.' % name
            return

        # change the json from the response into a dict of data and store it
        # into the toondata object that was passed in.
        jsondata = json.loads(response.content)
        toondata.update(jsondata);

        # Blizzard's API will return an error if it couldn't retrieve the data
        # for some reason.  Check for this and log it if it fails.  Note that
        # this response doesn't contain the toon's name so it has to be added
        # in afterwards.
        if 'status' in jsondata and jsondata['status'] == 'nok':
            print('Blizzard API failed to find toon %s for reason: %s' %
                  (name.encode('ascii','ignore'), jsondata['reason']))
            toondata['toon'] = name
            toondata['reason'] = "Error retrieving data for %s from Blizzard API: %s" % (name, jsondata['reason'])
            return

        print "got good results for %s" % name.encode('ascii','ignore')

        # For each toon, update the statistics for the group as a whole
        if toondata['main'] == True:
            groupstats.ilvlmains += 1
            groupstats.totalilvl += jsondata['items']['averageItemLevel']
            groupstats.totalilvleq += jsondata['items']['averageItemLevelEquipped']

            toonclass = classes[jsondata['class']]
            if toonclass in ['Paladin','Warrior','Death Knight']:
                groupstats.plate += 1
            elif toonclass in ['Mage','Priest','Warlock']:
                groupstats.cloth += 1
            elif toonclass in ['Druid','Monk','Rogue']:
                groupstats.leather += 1
            elif toonclass in ['Hunter','Shaman']:
                groupstats.mail += 1

            if toonclass in ['Paladin','Priest','Warlock']:
                groupstats.conq += 1
            elif toonclass in ['Warrior','Hunter','Shaman','Monk']:
                groupstats.prot += 1
            elif toonclass in ['Death Knight','Druid','Mage','Rogue']:
                groupstats.vanq += 1

    def create_callback(self, rpc, name, toondata, groupstats, classes):
        return lambda: self.handle_result(rpc, name, toondata, groupstats, classes)

class Editor(webapp2.RequestHandler):
    def get(self, nrealm, ngroup):
        self.editGroup(nrealm, ngroup)

    def editGroup(self, nrealm, ngroup):

        # load the list of realms from the datastore that was loaded by the
        # /loadrealms service
        q = Realm.query(namespace='Realms')
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
        print realms
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
        results = db_query.fetch(5)

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
        results = db_query.fetch(5)

        if ((len(results) != 0) and
            sha256_crypt.verify(self.request.get('pw'),
                                results[0].password) != True):
            self.response.write('Password did not match for this group!')
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
        print self.request.get('json').strip()
        jsondata = json.loads(self.request.get('json').strip())
        print 'number of toons saved: %d' % len(jsondata['toons'])

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

        self.loadGroup(group)

    def loadGroup(self, results):

        # Get the group data from the results
        toonlist = results.toons
        realm = results.nrealm

        # Query ndb for the full realm name based on the results
        rq = Realm.query(Realm.slug == realm, namespace='Realms')
        rqres = rq.fetch()
        frealm = rqres[0].realm

        q = ClassEntry.query()
        res = q.fetch()

        classes = dict()
        for c in res:
            classes[c.classId] = c.name

        groupstats = GroupStats()

        # Loop through the list of toons and start building up a list of dicts
        # with all of the data for each toon.  While doing so, set up a bunch
        # of async urlfetches to get the detailed data from the Blizzard API.
        # We'll loop back through and get all of the data once the fetches have
        # been created.
        data = list()

        importer = APIImporter()
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

    # Callback that handles the result of the call to the Blizzard API.  This will fill in
    # the toondata dict for the requested toon with either data from Battle.net or with an
    # error message to display on the page.
    def handle_result(self, rpc, name, toondata, groupstats, classes):

        try:
            response = rpc.get_result()
        except urlfetch_errors.DeadlineExceededError:
            print('urlfetch threw DeadlineExceededError on toon %s' % name.encode('ascii','ignore'))
            toondata['toon'] = name
            toondata['status'] = 'nok'
            toondata['reason'] = 'Timeout retrieving data from Battle.net for %s.  Refresh page to try again.' % name
            return
        except urlfetch_errors.DownloadError:
            print('urlfetch threw DownloadError on toon %s' % name.encode('ascii','ignore'))
            toondata['toon'] = name
            toondata['status'] = 'nok'
            toondata['reason'] = 'Network error retrieving data from Battle.net for toon %s.  Refresh page to try again.' % name
            return
        except:
            print('urlfetch threw unknown exception on toon %s' % name.encode('ascii','ignore'))
            toondata['toon'] = name
            toondata['status'] = 'nok'
            toondata['reason'] = 'Unknown error retrieving data from Battle.net for toon %s.  Refresh page to try again.' % name
            return

        # change the json from the response into a dict of data and store it
        # into the toondata object that was passed in.
        jsondata = json.loads(response.content)
        toondata.update(jsondata);

        # Blizzard's API will return an error if it couldn't retrieve the data
        # for some reason.  Check for this and log it if it fails.  Note that
        # this response doesn't contain the toon's name so it has to be added
        # in afterwards.
        if 'status' in jsondata and jsondata['status'] == 'nok':
            print('Blizzard API failed to find toon %s for reason: %s' %
                  (name.encode('ascii','ignore'), jsondata['reason']))
            toondata['toon'] = name
            toondata['reason'] = "Error retrieving data for %s from Blizzard API: %s" % (name, jsondata['reason'])
            return

        print "got good results for %s" % name.encode('ascii','ignore')

        # For each toon, update the statistics for the group as a whole
        if toondata['sub'] == '0':
            groupstats.ilvlmains += 1
            groupstats.totalilvl += jsondata['items']['averageItemLevel']
            groupstats.totalilvleq += jsondata['items']['averageItemLevelEquipped']

            toonclass = classes[jsondata['class']]
            if toonclass in ['Paladin','Warrior','Death Knight']:
                groupstats.plate += 1
            elif toonclass in ['Mage','Priest','Warlock']:
                groupstats.cloth += 1
            elif toonclass in ['Druid','Monk','Rogue']:
                groupstats.leather += 1
            elif toonclass in ['Hunter','Shaman']:
                groupstats.mail += 1

            if toonclass in ['Paladin','Priest','Warlock']:
                groupstats.conq += 1
            elif toonclass in ['Warrior','Hunter','Shaman','Monk']:
                groupstats.prot += 1
            elif toonclass in ['Death Knight','Druid','Mage','Rogue']:
                groupstats.vanq += 1

    def create_callback(self, rpc, name, toondata, groupstats, classes):
        return lambda: self.handle_result(rpc, name, toondata, groupstats, classes)

class UpdateDB(webapp2.RequestHandler):
    def get(self):
        # query the NDB for the old data
        db_query = Group.query()
        oldresults = db_query.fetch()

        for old in oldresults:
            new = Groupv2()
            new.groupname = old.groupname
            new.ngroup = old.ngroup
            new.nrealm = old.nrealm
            new.password = old.password
            new.lastvisited = datetime.now()
            for oldt in old.toons:
                newt = Toonv2()
                if ',' in oldt:
                    toonname,toonrealm,toonsub = oldt.split(',')
                    newt.name = toonname
                    newt.role = 'dps'
                    
                    if (toonrealm == '0'):
                        newt.realm = old.nrealm
                    else:
                        newt.realm = toonrealm

                    if (toonsub == '0'):
                        newt.main = True
                    else:
                        newt.main = False
                else:
                    newt.name = oldt
                    newt.role = 'dps'
                    newt.main = True
                    newt.realm = old.nrealm
                new.toons.append(newt);
            new.toons = sorted(new.toons, key=lambda s: s.name.lower())
                
            new.put()
