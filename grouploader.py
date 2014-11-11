# -*- coding: utf-8 -*-

#!/usr/bin/env python

import webapp2
import json,math,sys,os
import jinja2
from google.appengine.ext import ndb
from google.appengine.api.memcache import Client
from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_errors
from passlib.hash import sha256_crypt

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'])

class Group(ndb.Model):
    nrealm = ndb.StringProperty(indexed=True)
    ngroup = ndb.StringProperty(indexed=True)
    groupname = ndb.StringProperty()
    toons = ndb.StringProperty(repeated=True)
    password = ndb.StringProperty()

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

class ClassData(ndb.Model):
    entries = ndb.StructuredProperty(ClassEntry, repeated=True)

class Loader(webapp2.RequestHandler):
    def get(self, nrealm, ngroup):
        # try to load the group info from the database
        db_query = Group.query(Group.nrealm==nrealm, Group.ngroup==ngroup)
        results = db_query.fetch(5)
        
        # if the group doesn't exist, drop into the interface to make a new
        # group
        if (len(results) == 0):
            self.redirect('/edit/%s/%s' % (nrealm, ngroup))
        
        # if the group exists, load the group from the blizzard API and
        # display it.
        # if the group doesn't exist, show the page to create a new
        # group.
        else:
            self.loadGroup(results[0])

    def post(self, nrealm, ngroup):
        # try to load the group info from the database
        db_query = Group.query(Group.nrealm==nrealm, Group.ngroup==ngroup)
        results = db_query.fetch(5)
        
        if ((len(results) != 0) and
            sha256_crypt.verify(self.request.get('pw'), results[0].password) != True):
            self.response.write('Password did not match for this group!')
            return
        
        group = None
        if (len(results) != 0):
            group = results[0]
        else:
            group = Group()
        
        group.nrealm = nrealm
        group.ngroup = ngroup
        group.groupname = self.request.get('group').strip()
        
        group.password = sha256_crypt.encrypt(self.request.get('pw'))
        toons = self.request.POST.getall('toons')
        subs = self.request.get('subfield').split(',')
        crossrealms = self.request.get('crfield').split(',')
        print 'number of toons saved: %d' % len(toons)

        # clear the old toon information and recreate it from the data from
        # the form
        del group.toons[:]
        for i in range(len(toons)):
            toon = "%s,%s,%s" % (toons[i], crossrealms[i], subs[i])
            group.toons.append(toon)

        group.toons = sorted(group.toons, key=lambda s: s.lower())
        group.put()

        self.loadGroup(group)

    def loadGroup(self, results):

        # Get the group data from the results
        toons = results.toons
        realm = results.nrealm
        
        # Query ndb for the full realm name based on the results
        rq = Realm.query(Realm.slug == realm, namespace='Realms')
        rqres = rq.fetch()
        frealm = rqres[0].realm
        
        q = APIKey.query()
        apikey = q.fetch()[0]

        q = ClassData.query()
        res = q.fetch()
        
        classes = dict()
        for c in res[0].entries:
            classes[c.classId] = c.name

        jsondata = list()
        
        totalilvl = 0
        totalilvleq = 0
        totalmains = 0
        totalsubs = 0

        clothcount = 0
        leathercount = 0
        mailcount = 0
        platecount = 0
        
        # rogue/mage/druid/dk tokens
        vanqcount = 0
        # paladin/priest/warlock tokens
        conqcount = 0
        # warrior/hunter/shaman/monk tokens
        protcount = 0
        
        # Request all of the toon data from the blizzard API and determine the group's ilvls,
        # armor type counts and token type counts.  subs are not included in the counts, since
        # they're not really part of the main group.
        for toon in toons:
            if ',' in toon:
                toonname,toonrealm,toonsub = toon.split(',')
                if (toonrealm == '0'):
                    toonrealm = realm
                    toonfrealm = frealm
                else:
                    rq2 = Realm.query(
                        Realm.slug == toonrealm, namespace='Realms')
                    rq2res = rq2.fetch()
                    toonfrealm = rq2res[0].realm
            else:
                toonname = toon
                toonsub = '0'
                toonrealm = realm
                toonfrealm = frealm

            try:
                url = 'https://us.api.battle.net/wow/character/%s/%s?fields=items,guild&locale=en_US&apikey=%s' % (toonrealm, toonname, apikey.key)
                response = urlfetch.fetch(url)
                data = json.loads(response.content)
            except urlfetch_errors.DeadlineExceededError:
                data = { 'toon': toonname, 'status' : 'rgi-url-timeout' }

            # a realm is received in the json data from the API, but we need to pass the
            # normalized value to the next stages.  ignore this one.
            data['toonrealm'] = toonrealm
            data['toonfrealm'] = toonfrealm
            data['sub'] = toonsub
            
            if 'status' in data and data['status'] == 'nok':
                print('Failed to find toon %s' % toonname.encode('utf-8'))
                data['toon'] = toonname
            else:
                if toonsub == '0':
                    totalmains += 1
                    totalilvl += data['items']['averageItemLevel']
                    totalilvleq += data['items']['averageItemLevelEquipped']
                    
                    toonclass = classes[data['class']]
                    if toonclass in ['Paladin','Warrior','Death Knight']:
                        platecount += 1
                    elif toonclass in ['Mage','Priest','Warlock']:
                        clothcount += 1
                    elif toonclass in ['Druid','Monk','Rogue']:
                        leathercount += 1
                    elif toonclass in ['Hunter','Shaman']:
                        mailcount += 1
                    
                    if toonclass in ['Paladin','Priest','Warlock']:
                        conqcount += 1
                    elif toonclass in ['Warrior','Hunter','Shaman','Monk']:
                        protcount += 1
                    elif toonclass in ['Death Knight','Druid','Mage','Rogue']:
                        vanqcount += 1
                else:
                    totalsubs += 1

            jsondata.append(data)

        # throw them at jinja to generate the actual html
        template_values = {
            'group' : results.groupname,
            'frealm' : frealm,
            'ngroup' : results.ngroup,
            'nrealm' : results.nrealm,
            'groupavgilvl' : totalilvl / totalmains,
            'groupavgeqp' : totalilvleq / totalmains,
        }
        template = JINJA_ENVIRONMENT.get_template('groupinfo-header.html')
        self.response.write(template.render(template_values))
        
        self.response.write('        <hr style="width:90%;clear: both"/><br/>\n')

        template_values = {
            'clothcount' : clothcount,
            'leathercount' : leathercount,
            'mailcount' : mailcount,
            'platecount' : platecount,
            'conqcount' : conqcount,
            'protcount' : protcount,
            'vanqcount' : vanqcount,
        }
        template = JINJA_ENVIRONMENT.get_template('groupinfo-armortokens.html')
        self.response.write(template.render(template_values))

        self.response.write('        <hr style="width:90%;clear: both"/><br/>\n')
        self.response.write('        <div style="font-size: 20px">Main Group</div>\n')
        self.response.write('        <br/>\n')

        
        self.response.write('        <div class="left">\n')

        # Loop through the data twice here to display the separate sections,
        # but don't actually loop through all of the data.  The lambda filters
        # filter the character data down to just the parts that are needed
        # for each loop.
        halfindex = math.ceil(totalmains / 2.0)
        for idx, char in enumerate(filter(lambda x: x['sub'] == '0', jsondata)):

            if (idx == halfindex):
                self.response.write('        </div>')
                self.response.write('        <div class="right">\n')
            
            self.addCharacter(char, results, classes)

        self.response.write('       </div>\n')
    
        # Now add the subs in the same way as above
        self.response.write('        <div style="font-size: 20px;clear: both">Subs</div>\n')
        self.response.write('        <br/>\n')
        self.response.write('        <div class="left">\n')

        halfindex = math.ceil(totalsubs / 2.0)
        for idx, char in enumerate(filter(lambda x: x['sub'] == '1', jsondata)):
            
            if (idx == halfindex):
                self.response.write('        </div>')
                self.response.write('        <div class="right">\n')
            
            self.addCharacter(char, results, classes)

        self.response.write('       </div>\n')
        
        self.response.write('    </body>\n')
        self.response.write('</html>')
        
    def addCharacter(self, char, results, classes):
        if 'status' in char and char['status'] == 'nok':
            template_values = {
                'name' : char['toon'],
                'avgilvl' : 0
            }
        elif 'status' in char and char['status'] == 'rgi-url-timeout':
            template_values = {
                'name' : char['toon'],
                'avgilvl' : -1
            }
        else:
           
            items = char['items']
            template_values = {
                'name' : char['name'],
                'frealm' : char['toonfrealm'],   # full realm name
                'nrealm' : results.nrealm,  # realm for group
                'realm' : char['toonrealm'],  # realm for toon (might not be == to nrealm)
                'guild' : char['guild']['name'] if 'guild' in char else None,
                'class' : classes[char['class']],
                'avgilvl' : char['items']['averageItemLevel'],
                'avgilvle' : char['items']['averageItemLevelEquipped'],
                'head' : items['head']['itemLevel'] if 'head' in items else None,
                'neck' : items['neck']['itemLevel'] if 'neck' in items else None,
                'shoulder' : items['shoulder']['itemLevel'] if 'shoulder' in items else None,
                'back' : items['back']['itemLevel'] if 'back' in items else None,
                'chest' : items['chest']['itemLevel'] if 'chest' in items else None,
                'wrist' : items['wrist']['itemLevel'] if 'wrist' in items else None,
                'hands' : items['hands']['itemLevel'] if 'hands' in items else None,
                'waist' : items['waist']['itemLevel'] if 'waist' in items else None,
                'legs' : items['legs']['itemLevel'] if 'legs' in items else None,
                'feet' : items['feet']['itemLevel'] if 'feet' in items else None,
                'finger1' : items['finger1']['itemLevel'] if 'finger1' in items else None,
                'finger2' : items['finger2']['itemLevel'] if 'finger2' in items else None,
                'trinket1' : items['trinket1']['itemLevel'] if 'trinket1' in items else None,
                'trinket2' : items['trinket2']['itemLevel'] if 'trinket2' in items else None,
                'mainHand' : items['mainHand']['itemLevel'] if 'mainHand' in items else None,
                'offHand' : items['offHand']['itemLevel'] if 'offHand' in items else None,
            }

        template = JINJA_ENVIRONMENT.get_template('groupinfo-toon.html')
        self.response.write(template.render(template_values))

class Editor(webapp2.RequestHandler):
    def get(self, nrealm, ngroup):
        self.editGroup(nrealm, ngroup)
    
    def editGroup(self, nrealm, ngroup):
        
        # load the list of realms from the datastore that was loaded by the
        # /loadrealms service
        q = Realm.query(namespace='Realms')
        realms = q.fetch()

        # try to load the group info from the database
        db_query = Group.query(Group.nrealm==nrealm, Group.ngroup==ngroup)
        queryresults = db_query.fetch(5)
        
        results = None
        if (len(queryresults) != 0):
            results = queryresults[0]

        # Loop through the results from the data store and create a list
        # of toon names, the markers for subs, and the markers for
        # cross-realm.  If there weren't any results, blank lists will be
        # passed to the template.
        names = list()
        subs = list()
        crs = list()
        if results != None:
            for toon in results.toons:
                if ',' in toon:
                    name,realm,sub = toon.split(',')
                    names.append(name)
                    subs.append(sub)
                    crs.append(realm)
                else:
                    names.append(toon)
                    subs.append('0')
                    crs.append('0')

        # throw them at jinja to generate the actual html
        template_values = {
            'group' : ngroup,
            'realm' : nrealm,
            'names' : names,
            'realms' : realms,
            'subs' : subs,
            'crs' : crs,
        }
        template = JINJA_ENVIRONMENT.get_template('editor.html')
        self.response.write(template.render(template_values))
